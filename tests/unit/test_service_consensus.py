"""Tests unitaires pour adam_api.services.consensus."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adam_api.services.consensus import _apply_vote, _resolve, try_resolve
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus


def _field(ocr_value: str = "ocr_val") -> MagicMock:
    df = MagicMock()
    df.ocr_value = ocr_value
    df.consensus_reached = False
    df.status = None
    df.resolved_value = None
    return df


def _proposal(value: str) -> MagicMock:
    p = MagicMock()
    p.value = value
    return p


# ---------------------------------------------------------------------------
# _apply_vote
# ---------------------------------------------------------------------------

def test_apply_vote_no_proposals_uses_ocr_value() -> None:
    df = _field(ocr_value="original")
    assert _apply_vote(df, []) is True
    assert df.consensus_reached is True
    assert df.resolved_value == "original"
    assert df.status == DocumentFieldStatus.VALIDATED.value


def test_apply_vote_majority_reached() -> None:
    df = _field()
    result = _apply_vote(df, [_proposal("A"), _proposal("A"), _proposal("B")])
    assert result is True
    assert df.consensus_reached is True
    assert df.resolved_value == "A"
    assert df.status == DocumentFieldStatus.VALIDATED.value


def test_apply_vote_no_majority_disputed() -> None:
    df = _field()
    result = _apply_vote(df, [_proposal("A"), _proposal("B")])
    assert result is False
    assert df.consensus_reached is False
    assert df.status == DocumentFieldStatus.DISPUTED.value


# ---------------------------------------------------------------------------
# _resolve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_dataset_not_found() -> None:
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    result = await _resolve(1, 99, db)
    assert result["status"] == "error"
    assert result["reason"] == "dataset introuvable"


@pytest.mark.asyncio
async def test_resolve_document_not_found() -> None:
    db = AsyncMock()
    dataset = MagicMock()
    db.get = AsyncMock(side_effect=[dataset, None])
    result = await _resolve(1, 1, db)
    assert result["status"] == "error"
    assert result["reason"] == "document introuvable"


@pytest.mark.asyncio
async def test_resolve_already_validated() -> None:
    db = AsyncMock()
    document = MagicMock()
    document.status = DocumentStatus.VALIDATED.value
    db.get = AsyncMock(side_effect=[MagicMock(), document])
    result = await _resolve(1, 1, db)
    assert result["status"] == "already_validated"


@pytest.mark.asyncio
async def test_resolve_waiting_not_enough_submitted() -> None:
    db = AsyncMock()
    dataset = MagicMock()
    dataset.required_operators = 3
    document = MagicMock()
    document.status = DocumentStatus.IN_PROGRESS.value
    db.get = AsyncMock(side_effect=[dataset, document])
    submitted_result = MagicMock()
    submitted_result.scalar_one.return_value = 1
    db.execute = AsyncMock(return_value=submitted_result)
    result = await _resolve(1, 1, db)
    assert result["status"] == "waiting"
    assert result["submitted_jobs"] == 1
    assert result["required_operators"] == 3


@pytest.mark.asyncio
async def test_resolve_all_fields_resolved() -> None:
    db = AsyncMock()
    dataset = MagicMock()
    dataset.required_operators = 2
    document = MagicMock()
    document.status = DocumentStatus.IN_PROGRESS.value
    db.get = AsyncMock(side_effect=[dataset, document])

    submitted_result = MagicMock()
    submitted_result.scalar_one.return_value = 2

    field = MagicMock()
    field.id = 1
    field.ocr_value = "val"
    fields_result = MagicMock()
    fields_result.scalars.return_value.all.return_value = [field]

    proposal = MagicMock()
    proposal.document_field_id = 1
    proposal.value = "val"
    proposals_result = MagicMock()
    proposals_result.scalars.return_value.all.return_value = [proposal, proposal]

    db.execute = AsyncMock(side_effect=[submitted_result, fields_result, proposals_result])
    result = await _resolve(1, 1, db)
    assert result["document_status"] == DocumentStatus.VALIDATED.value
    assert result["fields_resolved"] == 1
    assert result["fields_disputed"] == 0


@pytest.mark.asyncio
async def test_resolve_disputed_fields() -> None:
    db = AsyncMock()
    dataset = MagicMock()
    dataset.required_operators = 2
    document = MagicMock()
    document.status = DocumentStatus.IN_PROGRESS.value
    db.get = AsyncMock(side_effect=[dataset, document])

    submitted_result = MagicMock()
    submitted_result.scalar_one.return_value = 2

    field = MagicMock()
    field.id = 1
    field.ocr_value = "val"
    fields_result = MagicMock()
    fields_result.scalars.return_value.all.return_value = [field]

    # tie → disputed
    proposals_result = MagicMock()
    proposals_result.scalars.return_value.all.return_value = [
        MagicMock(document_field_id=1, value="A"),
        MagicMock(document_field_id=1, value="B"),
    ]

    db.execute = AsyncMock(side_effect=[submitted_result, fields_result, proposals_result])
    result = await _resolve(1, 1, db)
    assert result["fields_disputed"] == 1
    assert result["fields_resolved"] == 0


# ---------------------------------------------------------------------------
# try_resolve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_try_resolve_handles_exception() -> None:
    with patch("adam_api.services.consensus.get_async_session") as mock_ctx:
        mock_db = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("adam_api.services.consensus._resolve", AsyncMock(side_effect=Exception("fail"))):
            result = await try_resolve(1, 1)
    assert result["error"] == "try_resolve echoue"
    assert result["document_id"] == 1
