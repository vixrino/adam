"""Verification manuelle du connecteur Mistral contre l'endpoint reel.

Prend un CERFA PDF (fictif uniquement : les valeurs extraites sont affichees)
ou un dossier d'images de pages, appelle le connecteur configure par le .env,
et affiche ce qui a ete detecte. Aucune base, aucune API interne : seul le
connecteur est exerce — c'est le CA-1 du ticket T5.

    python scripts/test_mistral_connector.py chemin/vers/cerfa.pdf
    python scripts/test_mistral_connector.py data/pvc/1/pages

Prerequis dans le .env : OCR_MOCK_ENABLED=false, MISTRAL_API_KEY,
MISTRAL_OCR_ENDPOINT, MISTRAL_CA_BUNDLE. Si le mock est actif, le script
le dit et s'arrete plutot que de faire croire a un test reel.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adam_api.core.config import settings  # noqa: E402
from adam_core.utils.pdf_render import render_pages_to_png  # noqa: E402
from adam_worker.connectors import connector_from_settings  # noqa: E402


def _page_images(target: Path) -> list[Path]:
    if target.is_dir():
        images = sorted(
            p for p in target.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")
        )
        if not images:
            raise SystemExit(f"aucune image de page dans {target}")
        return images
    if target.suffix.lower() == ".pdf":
        output_dir = Path(tempfile.mkdtemp(prefix="mistral_pages_"))
        images = render_pages_to_png(target, output_dir)
        print(f"{len(images)} page(s) rendues dans {output_dir}")
        return images
    raise SystemExit(f"attendu un PDF ou un dossier d'images, recu {target}")


async def _main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    if settings.ocr_mock_enabled:
        raise SystemExit("OCR_MOCK_ENABLED=true : mettre false dans le .env pour tester Mistral")

    images = _page_images(Path(sys.argv[1]))
    connector = connector_from_settings(settings)
    print(f"connecteur : {connector.name}")
    print(f"endpoint   : {settings.mistral_ocr_endpoint}")

    doc = await connector.extract(images)

    if doc is None:
        print("\nAucun champ detecte (extract a rendu None).")
        print("Normal sur un document vierge ; suspect sur un CERFA rempli.")
        return

    detected = [(page, kv) for page, _, kv in doc.iter_kv_pairs() if kv.value is not None]
    empty = sum(1 for _, _, kv in doc.iter_kv_pairs() if kv.value is None)
    print(f"\n{len(detected)} champ(s) detecte(s), {empty} attendu(s) sans valeur\n")
    for page, kv in detected:
        print(f"  p{page}  {kv.id:55s} [{kv.value.type}] = {kv.extracted_value}")


if __name__ == "__main__":
    asyncio.run(_main())
