"""Tests unitaires adam_core/utils/pdf_render.py"""

from pathlib import Path

import fitz
import pytest

from adam_core.utils.pdf_render import (
    PdfRenderError,
    page_image_relative_path,
    pages_relative_dir,
    render_pages_to_png,
)


def _make_pdf(path: Path, page_count: int) -> None:
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(path))
    doc.close()


def test_pages_relative_dir() -> None:
    assert pages_relative_dir(42) == Path("42") / "pages"


def test_page_image_relative_path() -> None:
    assert page_image_relative_path(42, 7) == Path("42") / "pages" / "0007.png"


def test_render_pages_to_png_creates_one_png_per_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, page_count=3)
    output_dir = tmp_path / "out"

    written = render_pages_to_png(pdf_path, output_dir)

    assert len(written) == 3
    assert [p.name for p in written] == ["0001.png", "0002.png", "0003.png"]
    for p in written:
        assert p.exists()
        assert p.stat().st_size > 0


def test_render_pages_to_png_single_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "single.pdf"
    _make_pdf(pdf_path, page_count=1)

    written = render_pages_to_png(pdf_path, tmp_path / "out")

    assert len(written) == 1


def test_render_pages_to_png_corrupt_pdf_raises(tmp_path: Path) -> None:
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not a pdf at all")

    with pytest.raises(PdfRenderError):
        render_pages_to_png(bad_pdf, tmp_path / "out")


def test_render_pages_to_png_no_partial_output_on_failure(tmp_path: Path) -> None:
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not a pdf at all")
    output_dir = tmp_path / "out"

    with pytest.raises(PdfRenderError):
        render_pages_to_png(bad_pdf, output_dir)

    assert not any(output_dir.glob("*.png")) if output_dir.exists() else True


def test_render_pages_to_png_cleans_up_partial_output_on_mid_render_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, page_count=3)
    output_dir = tmp_path / "out"

    original_save = fitz.Pixmap.save
    calls = {"n": 0}

    def flaky_save(self: fitz.Pixmap, path: str, *args: object, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("page illisible")
        original_save(self, path, *args, **kwargs)

    monkeypatch.setattr(fitz.Pixmap, "save", flaky_save)

    with pytest.raises(PdfRenderError):
        render_pages_to_png(pdf_path, output_dir)

    assert list(output_dir.glob("*.png")) == []
