"""Diagnostic de la pre-alimentation, du document en base jusqu'au merge.

PrepopulationWorker peut produire un document entierement vide sans lever la
moindre erreur : un OCR qui ne detecte rien et un schema dont aucune cle ne
correspond donnent le meme resultat silencieux. Ce script rejoue sa sequence
sur un document reel, palier par palier, et nomme le premier qui casse.

    uv run python scripts/diag_prepopulation.py <document_id>
    uv run python scripts/diag_prepopulation.py <document_id> --show-values
    uv run python scripts/diag_prepopulation.py <document_id> --api=http://127.0.0.1:8000

Aucune ecriture : ni champ cree, ni statut modifie. Les valeurs extraites sont
masquees par defaut (IBAN, NIR) ; --show-values les affiche, a reserver aux
documents fictifs.

Autonomie des imports
---------------------
Le script ne tire du worker que le connecteur. L'origine HTTP de l'API, le
chemin des images et la cle semantique sont redefinis ici plutot qu'importes :
ce sont trois lignes, et les importer ferait dependre le diagnostic de la
version exacte du poller — qui differe entre les deux miroirs du projet, ou le
nom de paquet change et ou _api_origin n'existe pas partout. Un outil de
diagnostic qui casse a l'import ne diagnostique rien.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

try:  # les deux miroirs du projet ne portent pas le meme nom de paquet
    from nota_api.core.config import settings
    from nota_core.core.config import get_core_settings
    from nota_core.db.session import get_async_session, init_engine
    from nota_core.models import Document, DocumentField, FieldSpec
    from nota_worker.connectors import connector_from_settings
except ImportError:  # pragma: no cover
    from adam_api.core.config import settings
    from adam_core.core.config import get_core_settings
    from adam_core.db.session import get_async_session, init_engine
    from adam_core.models import Document, DocumentField, FieldSpec
    from adam_worker.connectors import connector_from_settings

API_PREFIX = "/api/v1"
SEP = "=" * 70

#: Adresses d'ecoute qui ne designent aucun hote joignable.
_WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]", ""}


#: Origine imposee par --api, qui court-circuite la lecture des settings.
_FORCED_ORIGIN: Optional[str] = None


def api_origin() -> str:
    """Origine HTTP de l'API, telle qu'un client doit la composer.

    api_host est l'adresse d'ECOUTE : le joker 0.0.0.0 dit a un serveur ou se
    mettre, pas a un client ou aller, et se rabat donc sur localhost. --api
    passe outre, pour une API servie derriere un autre nom ou un autre port.
    """
    if _FORCED_ORIGIN:
        return _FORCED_ORIGIN
    host = str(getattr(settings, "api_host", "127.0.0.1") or "127.0.0.1").strip()
    if host in _WILDCARD_HOSTS:
        host = "127.0.0.1"
    return f"http://{host}:{getattr(settings, 'api_port', 8000)}"


def pages_dir(file_id: int) -> Path:
    """Repertoire des images de page, convention du pipeline d'ingestion."""
    return Path(settings.pvc_mount_path) / str(file_id) / "pages"


def semantic_key(section_id: Optional[str], field_key: str) -> str:
    """Cle "section.champ" qui rapproche un FieldSpec d'un KVPair."""
    if not section_id or field_key.startswith(f"{section_id}."):
        return field_key
    return f"{section_id}.{field_key}"


def line(title: str) -> None:
    print("\n" + SEP)
    print(title)
    print(SEP)


def get_json(client: httpx.Client, path: str) -> Any:
    response = client.get(f"{api_origin()}{API_PREFIX}{path}")
    if response.status_code >= 400:
        raise RuntimeError(f"GET {path} -> {response.status_code} {response.text[:200]}")
    return response.json()


async def main() -> None:
    global _FORCED_ORIGIN
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_values = "--show-values" in sys.argv
    for flag in sys.argv[1:]:
        if flag.startswith("--api="):
            _FORCED_ORIGIN = flag.split("=", 1)[1].rstrip("/")
    if len(args) != 1:
        raise SystemExit(__doc__)
    document_id = int(args[0])

    # -- 1. Le document -----------------------------------------------------
    # L'engine est global et paresseux : hors des points d'entree de l'API et
    # des workers, personne ne l'a initialise, et get_async_session leve avant
    # la premiere requete. Un script autonome doit donc l'amorcer lui-meme.
    line(f"1. Document {document_id}")
    init_engine(get_core_settings().async_database_url, echo=False)
    async with get_async_session() as db:
        row = (
            await db.execute(
                select(Document.dataset_id, Document.file_id, Document.status).where(
                    Document.id == document_id
                )
            )
        ).one_or_none()
    if row is None:
        raise SystemExit(f"document {document_id} introuvable")
    dataset_id, file_id = int(row.dataset_id), int(row.file_id)
    print(f"  dataset_id = {dataset_id}")
    print(f"  file_id    = {file_id}")
    print(f"  status     = {row.status}")

    # -- 2. Les images de page ---------------------------------------------
    line("2. Images de page lues par le worker")
    directory = pages_dir(file_id)
    print(f"  repertoire = {directory}")
    if not directory.is_dir():
        print("\n  ECHEC : repertoire absent. Le connecteur recoit une liste vide,")
        print("  tous les champs sont crees sans valeur, et rien n'est logue.")
        return
    images = sorted(directory.glob("*.png"))
    print(f"  {len(images)} image(s) : {', '.join(p.name for p in images[:12])}")
    if not images:
        print("\n  ECHEC : aucune image. Meme consequence que ci-dessus.")
        return

    # -- 3. Le connecteur ---------------------------------------------------
    line("3. Connecteur OCR")
    connector = connector_from_settings(settings)
    print(f"  connecteur = {connector.name}")
    if connector.name == "mock":
        print("  ATTENTION : mock construit sans detected_keys, il rend un document vide.")
    else:
        print(f"  endpoint   = {settings.mistral_ocr_endpoint}")
        decrites = sorted(getattr(connector, "page_fields", {}) or {})
        print(f"  pages decrites par le schema CERFA : {decrites}")
        hors = [n for n in range(1, len(images) + 1) if n not in decrites]
        print(f"  pages du document non soumises     : {hors}")

    ocr = await connector.extract(images)
    close = getattr(connector, "aclose", None)
    if close is not None:
        await close()

    if ocr is None:
        print("\n  ECHEC : extract() rend None, aucun champ detecte sur aucune page.")
        print("  Verifier que la pagination du PDF correspond aux pages decrites.")
        return

    pairs = [(page, kv) for page, _, kv in ocr.iter_kv_pairs() if kv.value is not None]
    print(f"\n  {len(pairs)} champ(s) detecte(s) par l'OCR")
    for page, kv in pairs[:10]:
        print(f"    p{page}  {kv.id:50s} = {kv.extracted_value if show_values else '***'}")
    if len(pairs) > 10:
        print(f"    ... et {len(pairs) - 10} autre(s)")
    if not pairs:
        print("\n  ECHEC : document rendu, mais aucun champ porte de valeur.")
        return

    # -- 4. Le schema attendu ----------------------------------------------
    line("4. Schema du dataset, via l'API")
    headers = (
        {"X-Internal-Token": settings.internal_api_key}
        if getattr(settings, "internal_api_key", "")
        else {}
    )
    with httpx.Client(timeout=30.0, headers=headers) as client:
        try:
            dataset = get_json(client, f"/datasets/{dataset_id}")
            schema_id = dataset.get("schema_id")
            if schema_id is None:
                print(f"  ECHEC : dataset {dataset_id} sans schema_id")
                return
            schema = get_json(client, f"/schemas/{int(schema_id)}")
        except (RuntimeError, httpx.HTTPError) as exc:
            print(f"  ECHEC : {exc}")
            print("  L'API doit tourner ; c'est par elle que le worker lit le schema.")
            return

    specs: List[Dict[str, Any]] = schema.get("field_specs", [])
    print(f"  schema_id  = {schema_id}")
    print(f"  nom        = {schema.get('name')}")
    print(f"  type       = {schema.get('document_type')}")
    print(f"  {len(specs)} field_spec(s)")
    schema_keys = {semantic_key(s.get("section_id"), s["field_key"]) for s in specs}
    for key in sorted(schema_keys)[:10]:
        print(f"    {key}")
    if len(schema_keys) > 10:
        print(f"    ... et {len(schema_keys) - 10} autre(s)")

    # -- 5. Le rapprochement ------------------------------------------------
    line("5. Rapprochement OCR <-> schema")
    ocr_keys = {kv.id for _, kv in pairs}
    commun = ocr_keys & schema_keys
    print(f"  cles OCR avec valeur : {len(ocr_keys)}")
    print(f"  cles du schema       : {len(schema_keys)}")
    print(f"  cles communes        : {len(commun)}")

    if commun:
        print(f"\n  OK : {len(commun)} champ(s) recevront une ocr_value.")
        orphelines = sorted(ocr_keys - schema_keys)
        if orphelines:
            print(f"  {len(orphelines)} cle(s) OCR sans field_spec, ignorees :")
            for key in orphelines[:5]:
                print(f"    {key}")
        return

    if not commun:
        print("\n  CAUSE TROUVEE : aucune cle commune.")
        print("  L'OCR detecte bien, mais le dataset pointe un autre schema que le CERFA.")
        print("  Le merger ne rapproche rien et cree tous les champs vides, sans erreur.")
        print("\n  Cles rendues par l'OCR :")
        for key in sorted(ocr_keys)[:5]:
            print(f"    {key}")
        print("  Cles declarees par le schema :")
        for key in sorted(schema_keys)[:5]:
            print(f"    {key}")

    # -- 6. Ce qui est reellement en base -----------------------------------
    # Les paliers precedents disent ce que le worker DEVRAIT ecrire s'il
    # tournait maintenant. Celui-ci dit ce qu'il a ecrit la fois ou il est
    # passe, ce qui n'est pas la meme chose : les champs d'un document ne sont
    # crees qu'une fois, et repointer son dataset apres coup ne les rejoue pas.
    line("6. DOCUMENT_FIELD reellement stockes")
    async with get_async_session() as db:
        rows = (
            await db.execute(
                select(
                    DocumentField.id,
                    DocumentField.ocr_value,
                    DocumentField.group_id,
                    FieldSpec.section_id,
                    FieldSpec.field_key,
                )
                .join(FieldSpec, FieldSpec.id == DocumentField.field_spec_id)
                .where(DocumentField.document_id == document_id)
                .order_by(DocumentField.id)
            )
        ).all()

    remplis = [r for r in rows if r.ocr_value is not None]
    print(f"  {len(rows)} champ(s) en base, {len(remplis)} avec une ocr_value")
    for r in remplis[:10]:
        key = semantic_key(r.section_id, r.field_key)
        group = f" [{r.group_id}]" if r.group_id else ""
        print(f"    {key}{group:20s} = {r.ocr_value if show_values else '***'}")
    if len(remplis) > 10:
        print(f"    ... et {len(remplis) - 10} autre(s)")

    if not rows:
        print("\n  Aucun champ : le worker n'est jamais passe sur ce document.")
        print("  Verifier qu'il tourne et que le document est en INGESTED.")
    elif not remplis and commun:
        print("\n  CAUSE TROUVEE : les champs ont ete crees AVANT le bon schema.")
        print("  La creation est idempotente : le worker ne rejoue pas un document")
        print("  deja pre-alimente, meme si le rapprochement donnerait des valeurs")
        print("  aujourd'hui. Supprimer les champs et repasser le document en")
        print("  INGESTED, ou ingerer le PDF a nouveau.")
    elif remplis:
        print("\n  La base porte bien les valeurs.")
        print("  Si l'API rend null, c'est la lecture qu'il faut regarder :")
        print("  GET /documents/{id} sans view=full ne renvoie aucun champ.")


if __name__ == "__main__":
    asyncio.run(main())
