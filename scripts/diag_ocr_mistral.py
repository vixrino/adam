"""Diagnostic de l'endpoint OCR Mistral, du .env jusqu'a une vraie page.

Le connecteur ne rend qu'un statut et jette le corps de la reponse, ce qui
suffit en production mais laisse un 404 indechiffrable pendant la mise en
route. Ce script refait la meme sequence en affichant tout, et par paliers :
configuration lue, modeles servis, route nue, route avec annotation, page
reelle. Le premier palier qui casse nomme la cause.

    uv run python scripts/diag_ocr_mistral.py
    uv run python scripts/diag_ocr_mistral.py chemin/vers/cerfa.pdf

Sans argument, les sondes utilisent une image 1x1 : la route et l'annotation
se verifient sans depenser un appel sur un document reel.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

try:
    from nota_api.core.config import settings
except ImportError:
    from adam_api.core.config import settings

PNG_1x1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "sonde",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
            "additionalProperties": False,
        },
    },
}


def line(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def post(base: str, payload: dict, verify, key: str):
    try:
        return httpx.post(
            base + "/v1/ocr",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            verify=verify,
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ECHEC RESEAU : {type(exc).__name__} : {exc}")
        return None


def show(response) -> int:
    if response is None:
        return -1
    print(f"  statut : {response.status_code}")
    print(f"  corps  : {response.text[:600]}")
    return response.status_code


def main() -> None:
    base = settings.mistral_ocr_endpoint.rstrip("/")
    key = settings.mistral_api_key
    verify = settings.mistral_ca_bundle or True

    line("1. Configuration lue")
    print(f"  ocr_mock_enabled    : {settings.ocr_mock_enabled}")
    print(f"  mistral_ocr_endpoint: {base or '(VIDE)'}")
    print(f"  mistral_ocr_model   : {settings.mistral_ocr_model!r}")
    print(f"  mistral_api_key     : {'renseignee' if key else '(VIDE)'}")
    print(f"  mistral_ca_bundle   : {settings.mistral_ca_bundle or '(vide -> CA systeme)'}")

    if settings.ocr_mock_enabled:
        print("\n  ARRET : OCR_MOCK_ENABLED=true, le connecteur reel n'est jamais construit.")
        return
    if not base or not key:
        print("\n  ARRET : endpoint ou cle absents du .env.")
        return

    line("2. Modeles servis")
    try:
        r = httpx.get(
            base + "/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            verify=verify,
            timeout=30,
        )
        print(f"  statut : {r.status_code}")
        data = r.json().get("data", [])
        ocr_ids = [m["id"] for m in data if m.get("capabilities", {}).get("ocr")]
        print(f"  modeles OCR : {ocr_ids or 'AUCUN'}")
        configured_ok = settings.mistral_ocr_model in ocr_ids
        print(f"  modele configure servi : {configured_ok}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ECHEC : {type(exc).__name__} : {exc}")
        return

    if not ocr_ids:
        print("\n  VERDICT : aucun modele OCR. Il faut passer en multimodal chat.")
        return

    probe_model = settings.mistral_ocr_model if configured_ok else ocr_ids[0]
    if not configured_ok:
        print(f"\n  ATTENTION : modele configure absent, sondes faites avec {probe_model!r}.")

    image = f"data:image/png;base64,{PNG_1x1}"

    line("3. POST /v1/ocr nu (image 1x1 valide)")
    s3 = show(post(base, {"model": probe_model, "document": {"type": "image_url", "image_url": image}}, verify, key))

    line("4. POST /v1/ocr + document_annotation_format")
    s4 = show(
        post(
            base,
            {
                "model": probe_model,
                "document": {"type": "image_url", "image_url": image},
                "document_annotation_format": FORMAT,
                "include_image_base64": False,
            },
            verify,
            key,
        )
    )

    s5 = None
    if len(sys.argv) > 1:
        line("5. POST /v1/ocr sur une vraie page du PDF")
        try:
            try:
                from nota_core.utils.pdf_render import render_pages_to_png
            except ImportError:
                from adam_core.utils.pdf_render import render_pages_to_png
            import tempfile

            pages = render_pages_to_png(Path(sys.argv[1]), Path(tempfile.mkdtemp()))
            raw = base64.b64encode(pages[0].read_bytes()).decode("ascii")
            real = f"data:image/png;base64,{raw}"
            resp = post(
                base,
                {
                    "model": probe_model,
                    "document": {"type": "image_url", "image_url": real},
                    "document_annotation_format": FORMAT,
                    "include_image_base64": False,
                },
                verify,
                key,
            )
            s5 = show(resp)
            if resp is not None and resp.is_success:
                print(f"  cles rendues : {list(resp.json().keys())}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ECHEC : {type(exc).__name__} : {exc}")

    line("VERDICT")
    if s3 == 404:
        print("  La route /v1/ocr n'existe pas sur ce deploiement, meme sans annotation.")
        print("  -> question a l'equipe de l'endpoint, pas un probleme de code.")
    elif s4 == 404 and s3 != 404:
        print("  La route existe mais document_annotation_format la fait basculer en 404 :")
        print("  l'annotation structuree n'est pas deployee. -> remonter a l'equipe.")
    elif not configured_ok:
        print(f"  MISTRAL_OCR_MODEL={settings.mistral_ocr_model!r} n'est pas servi.")
        print(f"  -> mets MISTRAL_OCR_MODEL={probe_model} dans le .env.")
    elif s5 is not None and s5 == 200:
        print("  Tout passe. Le connecteur devrait marcher tel quel : relance test_mistral_connector.py.")
    elif s4 == 200:
        print("  Route et annotation OK sur une image 1x1. Relance avec le PDF en argument.")
    else:
        print(f"  Cas non couvert : s3={s3} s4={s4} s5={s5}. Colle cette sortie.")


if __name__ == "__main__":
    main()
