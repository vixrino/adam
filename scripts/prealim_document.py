"""
scripts/prealim_document.py

Pre-alimente un DOCUMENT : cree un DOCUMENT_FIELD vide (statut PENDING) pour
chaque FIELD_SPEC du schema, comme le ferait un resultat OCR sans aucune valeur
reconnue.

Pourquoi ce script

seed.py pose un document deja pre-alimente a partir de valeurs OCR fictives.
Ici on veut l'inverse : partir d'un document nu et lui accrocher la grille de
champs d'un schema, sans inventer de donnees. C'est l'etat dans lequel un
operateur prend la main quand l'OCR n'a rien rempli, ou quand on teste l'IHM
d'annotation sur un formulaire vierge.

Comment

Le script passe par l'API, endpoint POST /ocr-results — le chemin "bulk" de
pre-alimentation. On lui envoie un SmartdocDocument minimal (aucune page, aucune
valeur) ; le serveur deplie alors tous les FIELD_SPEC du schema du dataset en
DOCUMENT_FIELD vides. OCR_RESULT porte une contrainte d'unicite sur
(document_id, dataset_id) : un document ne peut etre pre-alimente qu'une fois.
Relancer le script sur un document deja fait ne touche a rien et le signale.

Le schema utilise est celui du dataset du document, pas un parametre libre :
--schema-id sert de garde-fou. Si le dataset pointe sur un autre schema, le
script s'arrete et affiche le bon identifiant. Deplacer un document vers un
schema different releve du dataset (PATCH /datasets/{id}), pas de ce script.

Usage :
    python scripts/prealim_document.py --schema-id 1 --document-id 4
    python scripts/prealim_document.py --schema-id 1 --document-id 4 --list
"""

import argparse
import os
import sys
from typing import Any, Dict

import httpx

DEFAULT_BASE_URL = os.environ.get("NOTA_API_URL", "http://localhost:8000/api/v1")
DEFAULT_TOKEN = os.environ.get("NOTA_INTERNAL_TOKEN", "abc")
SEPARATOR = "-" * 70


def _minimal_smartdoc(document_id: int) -> Dict[str, Any]:
    """SmartdocDocument valide et vide : le contrat impose une version, un id,
    un page_count et au moins une cle de metadata ; les pages peuvent manquer."""
    return {
        "smartdoc_version": "0.3",
        "document_id": f"prealim-doc-{document_id}",
        "coordinate_unit": "pixel",
        "page_count": 1,
        "pages": [],
        "metadata": {"source": "prealim_document.py"},
    }


def _get(client: httpx.Client, path: str, **params: Any) -> Any:
    resp = client.get(path, params=params or None)
    resp.raise_for_status()
    return resp.json()


def _find_dataset_id(client: httpx.Client, document_id: int) -> int:
    """dataset_id du document. GET /documents/{id} ne le renvoie pas ; la liste
    (DocumentOut) si. On la balaye largement plutot que d'ajouter un endpoint."""
    for doc in _get(client, "/documents", limit=100000):
        if doc["id"] == document_id:
            return doc["dataset_id"]
    raise SystemExit(f"  document {document_id} introuvable.")


def print_overview(schema: Dict[str, Any]) -> None:
    """Apercu des champs du schema, sans rien creer."""
    specs = sorted(
        schema["field_specs"],
        key=lambda s: (s["page"], s["display_order"]),
    )
    current: tuple = ()
    for spec in specs:
        header = (spec["page"], spec["section_id"], spec["group_id"])
        if header != current:
            current = header
            group = f" [{spec['group_id']}]" if spec["group_id"] else ""
            print(f"\n  page {spec['page']} - {spec['section_label']}{group}")
        print(f"      {spec['field_key']:<28} {spec['value_type']:<8} {spec['display_label']}")
    print(f"\n  {len(specs)} champ(s) au total")


def prealim(args: argparse.Namespace) -> None:
    headers = {"X-Internal-Token": args.token}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=30.0) as client:
        schema = _get(client, f"/schemas/{args.schema_id}")
        print(f"  schema {schema['id']} : {schema['name']} "
              f"({len(schema['field_specs'])} field_spec(s))")

        if args.list:
            print_overview(schema)
            print(f"\n{SEPARATOR}")
            return

        dataset_id = _find_dataset_id(client, args.document_id)
        dataset = _get(client, f"/datasets/{dataset_id}")
        if dataset["schema_id"] != args.schema_id:
            raise SystemExit(
                f"  document {args.document_id} depend du dataset {dataset_id}, "
                f"verrouille sur le schema {dataset['schema_id']}, pas {args.schema_id}.\n"
                f"  Relancer avec --schema-id {dataset['schema_id']}."
            )

        if _get(client, "/ocr-results", document_id=args.document_id):
            print("  document deja pre-alimente (OCR_RESULT present) : rien a faire.")
            return

        payload = {
            "document_id": args.document_id,
            "dataset_id": dataset_id,
            "raw_json": _minimal_smartdoc(args.document_id),
        }
        resp = client.post("/ocr-results", json=payload)
        resp.raise_for_status()
        out = resp.json()

    print(f"  document {args.document_id} <- schema {args.schema_id} (dataset {dataset_id})")
    print(f"  {out['document_fields_created']} champ(s) cree(s), "
          f"{out['document_fields_skipped']} ignore(s) (deja presents)")
    print(f"  statut du document : {out['document_status']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-alimente un document avec les champs vides d'un schema"
    )
    parser.add_argument("--schema-id", type=int, required=True)
    parser.add_argument("--document-id", type=int, required=True)
    parser.add_argument(
        "--list", action="store_true",
        help="Affiche les champs du schema, sans toucher au document",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"defaut: {DEFAULT_BASE_URL}")
    parser.add_argument("--token", default=DEFAULT_TOKEN,
                        help="valeur de l'en-tete X-Internal-Token")
    args = parser.parse_args()

    print(SEPARATOR)
    print("Pre-alimentation d'un document")
    print(SEPARATOR)
    try:
        prealim(args)
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except ValueError:
            detail = exc.response.text
        raise SystemExit(f"  {exc.request.method} {exc.request.url} "
                         f"-> {exc.response.status_code} {detail}")
    except httpx.RequestError as exc:
        raise SystemExit(f"  connexion impossible ({exc}). Serveur lance sur {args.base_url} ?")
    print(SEPARATOR)


if __name__ == "__main__":
    sys.exit(main())
