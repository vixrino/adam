"""Tests unitaires pour adam_api.services.ingestion."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pymupdf
import pytest

from adam_api.services.ingestion import (
    get_or_create_file,
    ingest_pdf,
    looks_like_pdf,
    pdf_page_count,
    pvc_relative_path,
)

# ---------------------------------------------------------------------------
# looks_like_pdf
# ---------------------------------------------------------------------------


def _minimal_valid_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def test_looks_like_pdf_valid_structure() -> None:
    assert looks_like_pdf(_minimal_valid_pdf()) is True


def test_looks_like_pdf_no_magic_bytes() -> None:
    assert looks_like_pdf(b"not pdf") is False


def test_looks_like_pdf_empty_content() -> None:
    assert looks_like_pdf(b"") is False


def test_looks_like_pdf_header_only_without_valid_structure() -> None:
    # magic bytes presents mais structure PDF absente/corrompue.
    assert looks_like_pdf(b"%PDF-1.4\ngarbage, not a real xref table") is False


# ---------------------------------------------------------------------------
# pvc_relative_path
# ---------------------------------------------------------------------------

_INGESTED_AT = datetime(2026, 1, 15, 13, 21, tzinfo=timezone.utc)


def test_pvc_relative_path_structure() -> None:
    path = pvc_relative_path(
        organisation_slug="dires",
        document_type="cerfa",
        ingested_at=_INGESTED_AT,
        file_name="cerfa_13594_sample.pdf",
        file_id=7,
    )
    assert path == Path("dires/cerfa/2026_01_15/7/cerfa_13594_sample.pdf")


def test_pvc_relative_path_keeps_original_file_name() -> None:
    path = pvc_relative_path(
        organisation_slug="dires",
        document_type="cerfa",
        ingested_at=_INGESTED_AT,
        file_name="Un Nom Bizarre (1).pdf",
        file_id=7,
    )
    assert path.name == "Un Nom Bizarre (1).pdf"


def test_pvc_relative_path_strips_directory_traversal_from_file_name() -> None:
    path = pvc_relative_path(
        organisation_slug="dires",
        document_type="cerfa",
        ingested_at=_INGESTED_AT,
        file_name="../../etc/passwd.pdf",
        file_id=7,
    )
    assert path == Path("dires/cerfa/2026_01_15/7/passwd.pdf")


def test_pvc_relative_path_no_collision_same_name_same_day_different_content() -> None:
    """Regression : deux contenus differents, meme nom et meme jour, ne doivent
    pas partager le meme chemin physique (sinon le second ecrase le premier).
    Le sous-dossier file_id rend le chemin unique par FILE."""
    common = dict(
        organisation_slug="dires",
        document_type="cerfa",
        ingested_at=_INGESTED_AT,
        file_name="demo_multipage.pdf",
    )
    path_v1 = pvc_relative_path(**common, file_id=7)
    path_v2 = pvc_relative_path(**common, file_id=8)
    assert path_v1 != path_v2
    assert path_v1.parent.parent == path_v2.parent.parent  # meme dossier date


# ---------------------------------------------------------------------------
# get_or_create_file
# ---------------------------------------------------------------------------

_LOCATION_KWARGS = dict(
    organisation_slug="dires",
    document_type="cerfa",
    file_name="doc.pdf",
)


@pytest.mark.asyncio
async def test_get_or_create_file_existing_on_disk(tmp_path: Path) -> None:
    existing_file = MagicMock()
    existing_file.file_path = "dires/cerfa/2025_06_01_0800/existing.pdf"
    abs_path = tmp_path / existing_file.file_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(b"existing")

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_file
    db.execute = AsyncMock(return_value=mock_result)

    file_row, created = await get_or_create_file(
        db, checksum="a" * 64, content=b"content", pvc_root=tmp_path, **_LOCATION_KWARGS
    )
    assert file_row is existing_file
    assert created is False


@pytest.mark.asyncio
async def test_get_or_create_file_existing_missing_from_disk(tmp_path: Path) -> None:
    existing_file = MagicMock()
    existing_file.file_path = "dires/cerfa/2025_06_01_0800/existing.pdf"
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_file
    db.execute = AsyncMock(return_value=mock_result)

    file_row, created = await get_or_create_file(
        db, checksum="b" * 64, content=b"restored", pvc_root=tmp_path, **_LOCATION_KWARGS
    )
    abs_path = tmp_path / existing_file.file_path
    assert abs_path.exists()
    assert abs_path.read_bytes() == b"restored"
    assert created is False


@pytest.mark.asyncio
async def test_get_or_create_file_new(tmp_path: Path) -> None:
    """Le chemin definitif contient le file_id attribue par l'INSERT."""
    new_file = MagicMock()
    new_file.id = 7

    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = new_file

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[select_result, insert_result])
    db.flush = AsyncMock()

    file_row, created = await get_or_create_file(
        db, checksum="c" * 64, content=b"new content", pvc_root=tmp_path, **_LOCATION_KWARGS
    )
    assert created is True
    assert file_row is new_file
    # le chemin est renseigne apres l'INSERT et contient le sous-dossier file_id
    assert "/7/doc.pdf" in file_row.file_path
    abs_path = tmp_path / file_row.file_path
    assert abs_path.exists()
    assert abs_path.read_bytes() == b"new content"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_file_concurrent_insert_loses_race(tmp_path: Path) -> None:
    """L'INSERT ON CONFLICT DO NOTHING ne retourne rien : on relit la ligne gagnante."""
    winning_file = MagicMock()

    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = None
    reselect_result = MagicMock()
    reselect_result.scalar_one.return_value = winning_file

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[select_result, insert_result, reselect_result])
    db.flush = AsyncMock()

    file_row, created = await get_or_create_file(
        db, checksum="d" * 64, content=b"content", pvc_root=tmp_path, **_LOCATION_KWARGS
    )
    assert file_row is winning_file
    assert created is False
    db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# ingest_pdf
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_pdf_already_exists(tmp_path: Path) -> None:
    db = AsyncMock()
    dataset = MagicMock()
    dataset.id = 1

    existing_doc = MagicMock()
    existing_doc.id = 42
    existing_doc.file_id = 7
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = (existing_doc, "dires/cerfa/2025_06_01_0800/doc.pdf")
    db.execute = AsyncMock(return_value=mock_result)

    result = await ingest_pdf(
        db,
        dataset,
        organisation_slug="dires",
        document_type="cerfa",
        file_name="doc.pdf",
        content=b"%PDF-1.4",
        pvc_root=tmp_path,
    )
    assert result["status"] == "already_exists"
    assert result["document_id"] == 42
    assert result["file_id"] == 7
    assert result["file_path"] == "dires/cerfa/2025_06_01_0800/doc.pdf"


@pytest.mark.asyncio
async def test_ingest_pdf_new_file_created(tmp_path: Path) -> None:
    db = AsyncMock()
    db.add = MagicMock()
    dataset = MagicMock()
    dataset.id = 1

    not_found = MagicMock()
    not_found.one_or_none.return_value = None
    db.execute = AsyncMock(return_value=not_found)
    db.flush = AsyncMock()

    file_mock = MagicMock()
    file_mock.id = 5
    file_mock.file_path = "dires/cerfa/2026_01_15/new.pdf"

    with patch(
        "adam_api.services.ingestion.get_or_create_file", AsyncMock(return_value=(file_mock, True))
    ):
        result = await ingest_pdf(
            db,
            dataset,
            organisation_slug="dires",
            document_type="cerfa",
            file_name="new.pdf",
            content=b"%PDF-1.4",
            pvc_root=tmp_path,
        )

    assert result["status"] == "created"
    assert result["file_id"] == 5
    assert result["file_path"] == "dires/cerfa/2026_01_15/new.pdf"


@pytest.mark.asyncio
async def test_ingest_pdf_file_reused(tmp_path: Path) -> None:
    db = AsyncMock()
    db.add = MagicMock()
    dataset = MagicMock()
    dataset.id = 1

    not_found = MagicMock()
    not_found.one_or_none.return_value = None
    db.execute = AsyncMock(return_value=not_found)
    db.flush = AsyncMock()

    file_mock = MagicMock()
    file_mock.id = 3
    file_mock.file_path = "dires/cerfa/2025_06_01_0800/dup.pdf"

    with patch(
        "adam_api.services.ingestion.get_or_create_file",
        AsyncMock(return_value=(file_mock, False)),
    ):
        result = await ingest_pdf(
            db,
            dataset,
            organisation_slug="dires",
            document_type="cerfa",
            file_name="dup.pdf",
            content=b"%PDF-1.4",
            pvc_root=tmp_path,
        )

    assert result["status"] == "created_file_reused"


# ---------------------------------------------------------------------------
# Controle du nombre de pages
# ---------------------------------------------------------------------------


def _pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_page_count() -> None:
    assert pdf_page_count(_pdf(12)) == 12
    assert pdf_page_count(b"pas un pdf") == 0


async def _ingest(tmp_path: Path, content: bytes, expected: int) -> tuple[dict, MagicMock]:
    db = AsyncMock()
    db.add = MagicMock()
    not_found = MagicMock()
    not_found.one_or_none.return_value = None
    db.execute = AsyncMock(return_value=not_found)
    db.flush = AsyncMock()
    dataset = MagicMock()
    dataset.id = 1
    file_mock = MagicMock()
    file_mock.id = 5
    file_mock.file_path = "dires/cerfa/2026_01_15/new.pdf"
    with patch(
        "adam_api.services.ingestion.get_or_create_file", AsyncMock(return_value=(file_mock, True))
    ):
        result = await ingest_pdf(
            db,
            dataset,
            organisation_slug="dires",
            document_type="cerfa",
            file_name="new.pdf",
            content=content,
            pvc_root=tmp_path,
            expected_page_count=expected,
        )
    return result, db.add.call_args.args[0]


@pytest.mark.asyncio
async def test_pdf_hors_taille_cree_en_error(tmp_path: Path) -> None:
    """Le document existe, tracable, mais en ERROR : PageImageWorker ne prenant
    que les RECEIVED, il ne sera ni rendu ni soumis a l'OCR."""
    result, document = await _ingest(tmp_path, _pdf(10), expected=12)

    assert result["status"] == "error"
    assert result["reason"] == "10 page(s) au lieu de 12"
    assert result["document_id"] is not None or document is not None
    assert document.status == "ERROR"
    assert document.metadata_["erreur"]["motif"] == "nombre_de_pages"
    assert document.metadata_["erreur"]["attendu"] == 12
    assert document.metadata_["erreur"]["recu"] == 10


@pytest.mark.asyncio
async def test_pdf_au_bon_nombre_de_pages_est_recu(tmp_path: Path) -> None:
    result, document = await _ingest(tmp_path, _pdf(12), expected=12)
    assert result["status"] == "created"
    assert document.status == "RECEIVED"
    assert document.metadata_ is None


@pytest.mark.asyncio
async def test_sans_nombre_de_pages_configure_aucun_controle(tmp_path: Path) -> None:
    result, document = await _ingest(tmp_path, _pdf(3), expected=0)
    assert result["status"] == "created"
    assert document.status == "RECEIVED"
