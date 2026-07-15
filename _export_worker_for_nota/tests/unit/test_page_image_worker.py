"""Tests unitaires nota_worker/page_image_worker.py"""

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from nota_core.enums.status import DocumentStatus
from nota_core.utils.pdf_render import PdfRenderError
from nota_worker import page_image_worker as worker_module
from nota_worker.page_image_worker import PageImageWorker


def _document(
    doc_id: int = 1, file_id: int = 10, status: str = DocumentStatus.RECEIVED.value
) -> Any:
    return SimpleNamespace(id=doc_id, file_id=file_id, status=status)


def _file(
    file_id: int = 10, file_path: str = "documents/aa/bb/aabb.pdf", page_count: int = 1
) -> Any:
    return SimpleNamespace(id=file_id, file_path=file_path, page_count=page_count)


class _FakeDb:
    """Simule l'AsyncSession pour db.execute(...).scalar_one_or_none() et db.get()."""

    def __init__(self, document: Any, file_row: Any) -> None:
        self._document = document
        self._file_row = file_row

    async def execute(self, _query: Any) -> Any:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._document
        result.scalars.return_value.all.return_value = [self._document.id] if self._document else []
        return result

    async def get(self, model: Any, pk: Any) -> Any:
        return self._file_row


def _patch_session(monkeypatch: pytest.MonkeyPatch, db: _FakeDb) -> None:
    @asynccontextmanager
    async def _fake_get_async_session() -> AsyncIterator[_FakeDb]:
        yield db

    monkeypatch.setattr(worker_module, "get_async_session", _fake_get_async_session)


@pytest.mark.asyncio
async def test_process_one_success_marks_in_progress_and_sets_page_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document()
    file_row = _file()
    db = _FakeDb(document, file_row)
    _patch_session(monkeypatch, db)

    written: List[Path] = [tmp_path / "0001.png", tmp_path / "0002.png"]
    monkeypatch.setattr(worker_module, "render_pages_to_png", lambda *_a, **_k: written)

    worker = PageImageWorker(pvc_root=tmp_path)
    await worker._process_one(document.id)

    assert document.status == DocumentStatus.IN_PROGRESS.value
    assert file_row.page_count == 2


@pytest.mark.asyncio
async def test_process_one_render_failure_leaves_document_received(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document()
    file_row = _file(page_count=1)
    db = _FakeDb(document, file_row)
    _patch_session(monkeypatch, db)

    def _boom(*_a: object, **_k: object) -> List[Path]:
        raise PdfRenderError("PDF corrompu")

    monkeypatch.setattr(worker_module, "render_pages_to_png", _boom)

    worker = PageImageWorker(pvc_root=tmp_path)
    await worker._process_one(document.id)

    assert document.status == DocumentStatus.RECEIVED.value
    assert file_row.page_count == 1  # inchange


@pytest.mark.asyncio
async def test_process_one_skips_document_already_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """with_for_update(skip_locked=True) renvoie None si un autre worker a deja
    la ligne, ou si le statut n'est plus RECEIVED (CA-6)."""
    document = _document(status=DocumentStatus.IN_PROGRESS.value)
    file_row = _file()
    db = _FakeDb(document, file_row)
    _patch_session(monkeypatch, db)

    called = {"n": 0}

    def _should_not_be_called(*_a: object, **_k: object) -> List[Path]:
        called["n"] += 1
        return []

    monkeypatch.setattr(worker_module, "render_pages_to_png", _should_not_be_called)

    worker = PageImageWorker(pvc_root=tmp_path)
    await worker._process_one(document.id)

    assert called["n"] == 0
    assert file_row.page_count == 1


@pytest.mark.asyncio
async def test_process_one_missing_file_row_logs_and_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document()
    db = _FakeDb(document, file_row=None)
    _patch_session(monkeypatch, db)

    worker = PageImageWorker(pvc_root=tmp_path)
    await worker._process_one(document.id)

    assert document.status == DocumentStatus.RECEIVED.value


@pytest.mark.asyncio
async def test_poll_processes_each_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = _document()
    file_row = _file()
    db = _FakeDb(document, file_row)
    _patch_session(monkeypatch, db)
    monkeypatch.setattr(
        worker_module, "render_pages_to_png", lambda *_a, **_k: [tmp_path / "0001.png"]
    )

    worker = PageImageWorker(pvc_root=tmp_path)
    processed = []
    worker._process_one = AsyncMock(side_effect=lambda doc_id: processed.append(doc_id))  # type: ignore[method-assign]

    await worker.poll()

    assert processed == [document.id]


@pytest.mark.asyncio
async def test_poll_isolates_failure_per_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = _document()
    db = _FakeDb(document, _file())
    _patch_session(monkeypatch, db)

    worker = PageImageWorker(pvc_root=tmp_path)
    worker._process_one = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    await worker.poll()  # ne doit pas lever malgre l'echec de _process_one
