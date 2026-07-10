"""Rendu des pages d'un PDF en images PNG (mini worker Sprint 3, ticket 8).

PyMuPDF (fitz) fait tout le travail : ouverture/validation du PDF et rendu
image page par page.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import fitz  # PyMuPDF

_PAGE_IMAGE_DPI = 150


class PdfRenderError(Exception):
    """PDF corrompu ou page illisible : aucune image partielle n'est laissee."""


def pages_relative_dir(file_id: int) -> Path:
    """Repertoire des images de page pour un FILE donne : file_id/pages/."""
    return Path(str(file_id)) / "pages"


def render_pages_to_png(pdf_path: Path, output_dir: Path) -> List[Path]:
    """Convertit chaque page de `pdf_path` en PNG dans `output_dir`.

    Retourne les chemins ecrits, dans l'ordre des pages (1-indexe, noms
    zero-padded pour un tri lexicographique correct). Leve PdfRenderError
    si le PDF est corrompu ou si une page ne peut pas etre rendue ; toute
    image deja ecrite pour ce PDF est alors supprimee (pas d'etat partiel).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    try:
        with fitz.open(str(pdf_path)) as doc:
            if doc.page_count == 0:
                raise PdfRenderError(f"PDF sans page ({pdf_path})")
            for page_number in range(1, doc.page_count + 1):
                page = doc.load_page(page_number - 1)
                pixmap = page.get_pixmap(dpi=_PAGE_IMAGE_DPI)
                image_path = output_dir / f"{page_number:04d}.png"
                pixmap.save(str(image_path))
                written.append(image_path)
    except PdfRenderError:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    except fitz.FileDataError as exc:
        for path in written:
            path.unlink(missing_ok=True)
        raise PdfRenderError(f"PDF illisible ({pdf_path}): {exc}") from exc
    except Exception as exc:
        for path in written:
            path.unlink(missing_ok=True)
        raise PdfRenderError(f"Echec de rendu PDF ({pdf_path}): {exc}") from exc

    return written
