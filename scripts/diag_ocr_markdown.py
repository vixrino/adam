"""Affiche le markdown brut que l'OCR rend pour une page, avant toute annotation.

Quand une valeur extraite surprend, deux causes tiennent : l'OCR a mal lu, ou
le modele d'annotation a invente. Elles se corrigent a des endroits opposes —
l'une ne se corrige meme pas du tout — et rien ne les distingue une fois
l'annotation faite. Ce script s'arrete donc au premier appel et montre le texte
tel qu'il arrive au second : la valeur y figure, ou elle n'y figure pas.

    uv run python scripts/diag_ocr_markdown.py chemin/vers/cerfa.pdf 10
    uv run python scripts/diag_ocr_markdown.py chemin/vers/cerfa.pdf 10 1947

Un troisieme argument filtre : seules les lignes qui le contiennent sont
affichees, en plus du compte total. Pratique sur une page dense, ou la valeur
cherchee se perd dans un tableau.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from nota_api.core.config import settings
    from nota_core.utils.pdf_render import render_pages_to_png
    from nota_worker.connectors.mistral import MistralOcrConnector
except ImportError:
    from adam_api.core.config import settings
    from adam_core.utils.pdf_render import render_pages_to_png
    from adam_worker.connectors.mistral import MistralOcrConnector


async def _main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    pdf = Path(sys.argv[1])
    page_number = int(sys.argv[2])
    motif = sys.argv[3] if len(sys.argv) > 3 else None

    if settings.ocr_mock_enabled:
        raise SystemExit("OCR_MOCK_ENABLED=true : le connecteur reel n'est pas construit.")

    images = render_pages_to_png(pdf, Path(tempfile.mkdtemp(prefix="markdown_")))
    if not 1 <= page_number <= len(images):
        raise SystemExit(f"page {page_number} hors du document ({len(images)} pages)")

    connector = MistralOcrConnector(
        api_key=settings.mistral_api_key,
        endpoint=settings.mistral_ocr_endpoint,
        model=settings.mistral_ocr_model,
        annotation_model=settings.mistral_annotation_model,
        timeout_seconds=float(settings.ocr_timeout_seconds),
        ca_bundle=settings.mistral_ca_bundle or None,
    )
    try:
        markdown, dims = await connector._read_page(images[page_number - 1], page_number)
    finally:
        await connector.aclose()

    lignes = markdown.splitlines()
    print(f"page {page_number} : {len(lignes)} lignes, dimensions {dims or '(absentes)'}\n")
    if motif is None:
        print(markdown)
        return

    trouvees = [ligne for ligne in lignes if motif in ligne]
    print(f"lignes contenant {motif!r} : {len(trouvees)}")
    for ligne in trouvees:
        print(f"  {ligne}")
    if not trouvees:
        print("  -> absente du markdown : la valeur vient du modele d'annotation,")
        print("     pas de l'OCR. Aucune consigne ne la fera disparaitre a coup sur.")


if __name__ == "__main__":
    asyncio.run(_main())
