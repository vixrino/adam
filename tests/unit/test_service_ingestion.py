"""Tests unitaires pour adam_api.services.ingestion."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adam_api.services.ingestion import (
    _get_or_create_file,
    ingest_pdf,
    looks_like_pdf,
    pvc_relative_path,
)
from adam_core.enums.status import DocumentStatus


# ---------------------------------------------------------------------------
# looks_like_pdf
# ---------------------------------------------------------------------------

def test_looks_like_pdf_magic_bytes() -> None:
    assert looks_like_pdf(b"%PDF-1.4 content") is True


def test_looks_like_pdf_no_magic_bytes() -> None:
    assert looks_like_pdf(b"not pdf") is False


def test_looks_like_pdf_empty_content() -> None:
    assert looks_like_pdf(b"") is False


# ---------------------------------------------------------------------------
# pvc_relative_path
# ---------------------------------------------------------------------------

def test_pvc_relative_path_structure() -> None:
    checksum = "abcdef1234567890"
    path = pvc_relative_path(checksum)
    assert path == Path("documents/ab/cd/abcdef1234567890.pdf")


def test_pvc_relative_path_uses_first_four_chars() -> None:
    checksum = "1234abcd"
    path = pvc_relative_path(checksum)
    assert path.parts[1] == "12"
    assert path.parts[2] == "34"


# ---------------------------------------------------------------------------
# _get_or_create_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_create_file_existing_on_disk(tmp_path: Path) -> None:
    checksum = "a" * 64
    abs_path = tmp_path / pvc_relative_path(checksum)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(b"existing")

    existing_file = MagicMock()
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_file
    db.execute = AsyncMock(return_value=mock_result)

    file_row, created = await _get_or_create_file(db, checksum=checksum, content=b"content", pvc_root=tmp_path)
    assert file_row is existing_file
    assert created is False


@pytest.mark.asyncio
async def test_get_or_create_file_existing_missing_from_disk(tmp_path: Path) -> None:
    checksum = "b" * 64
    existing_file = MagicMock()
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_file
    db.execute = AsyncMock(return_value=mock_result)

    file_row, created = await _get_or_create_file(db, checksum=checksum, content=b"restored", pvc_root=tmp_path)
    abs_path = tmp_path / pvc_relative_path(checksum)
    assert abs_path.exists()
    assert abs_path.read_bytes() == b"restored"
    assert created is False


@pytest.mark.asyncio
async def test_get_or_create_file_new(tmp_path: Path) -> None:
    checksum = "c" * 64
    new_file = MagicMock()

    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = new_file

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[select_result, insert_result])
    db.flush = AsyncMock()

    file_row, created = await _get_or_create_file(db, checksum=checksum, content=b"new content", pvc_root=tmp_path)
    abs_path = tmp_path / pvc_relative_path(checksum)
    assert abs_path.exists()
    assert created is True
    assert file_row is new_file
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_file_concurrent_insert_loses_race(tmp_path: Path) -> None:
    """L'INSERT ON CONFLICT DO NOTHING ne retourne rien : on relit la ligne gagnante."""
    checksum = "d" * 64
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

    file_row, created = await _get_or_create_file(db, checksum=checksum, content=b"content", pvc_root=tmp_path)
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
    mock_result.scalar_one_or_none.return_value = existing_doc
    db.execute = AsyncMock(return_value=mock_result)

    result = await ingest_pdf(db, dataset, file_name="doc.pdf", content=b"%PDF-1.4", pvc_root=tmp_path)
    assert result["status"] == "already_exists"
    assert result["document_id"] == 42
    assert result["file_id"] == 7


@pytest.mark.asyncio
async def test_ingest_pdf_new_file_created(tmp_path: Path) -> None:
    db = AsyncMock()
    db.add = MagicMock()
    dataset = MagicMock()
    dataset.id = 1

    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=not_found)
    db.flush = AsyncMock()

    file_mock = MagicMock()
    file_mock.id = 5

    with patch("adam_api.services.ingestion._get_or_create_file", AsyncMock(return_value=(file_mock, True))):
        result = await ingest_pdf(db, dataset, file_name="new.pdf", content=b"%PDF-1.4", pvc_root=tmp_path)

    assert result["status"] == "created"
    assert result["file_id"] == 5
    assert result["file_reused"] is False


@pytest.mark.asyncio
async def test_ingest_pdf_file_reused(tmp_path: Path) -> None:
    db = AsyncMock()
    db.add = MagicMock()
    dataset = MagicMock()
    dataset.id = 1

    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=not_found)
    db.flush = AsyncMock()

    file_mock = MagicMock()
    file_mock.id = 3

    with patch("adam_api.services.ingestion._get_or_create_file", AsyncMock(return_value=(file_mock, False))):
        result = await ingest_pdf(db, dataset, file_name="dup.pdf", content=b"%PDF-1.4", pvc_root=tmp_path)

    assert result["status"] == "created"
    assert result["file_reused"] is True
