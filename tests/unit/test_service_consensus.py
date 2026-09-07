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
        with patch(
            "adam_api.services.consensus._resolve", AsyncMock(side_effect=Exception("fail"))
        ):
            result = await try_resolve(1, 1)
    assert result["error"] == "try_resolve echoue"
    assert result["document_id"] == 1


# ---------------------------------------------------------------------------
# Le cas a deux operateurs
# ---------------------------------------------------------------------------
#
# C'est la configuration nominale des datasets (required_operators=2), et la
# seule ou la regle de majorite stricte, `top_count > len(values) / 2`, n'admet
# aucun partage : a deux voix, il faut l'unanimite. Ces tests fixent ce que
# fait le service dans les quatre situations qu'un lot a deux operateurs
# rencontre reellement.


def _dataset_and_document(required_operators: int = 2) -> tuple[MagicMock, MagicMock]:
    dataset = MagicMock()
    dataset.required_operators = required_operators
    document = MagicMock()
    document.status = DocumentStatus.IN_PROGRESS.value
    return dataset, document


def _field_with_id(field_id: int, ocr_value: str = "ocr_val") -> MagicMock:
    field = _field(ocr_value=ocr_value)
    field.id = field_id
    return field


def _proposal_for(field_id: int, value: str) -> MagicMock:
    proposal = _proposal(value)
    proposal.document_field_id = field_id
    return proposal


def _db_for(
    dataset: MagicMock,
    document: MagicMock,
    submitted: int,
    fields: list,
    proposals: list,
) -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(side_effect=[dataset, document])
    submitted_result = MagicMock()
    submitted_result.scalar_one.return_value = submitted
    fields_result = MagicMock()
    fields_result.scalars.return_value.all.return_value = fields
    proposals_result = MagicMock()
    proposals_result.scalars.return_value.all.return_value = proposals
    db.execute = AsyncMock(side_effect=[submitted_result, fields_result, proposals_result])
    return db


class TestDeuxOperateurs:
    @pytest.mark.asyncio
    async def test_les_deux_sont_d_accord_le_document_est_valide(self) -> None:
        dataset, document = _dataset_and_document()
        field = _field_with_id(1)
        db = _db_for(
            dataset,
            document,
            submitted=2,
            fields=[field],
            proposals=[_proposal_for(1, "MARTEL"), _proposal_for(1, "MARTEL")],
        )

        result = await _resolve(1, 1, db)

        assert result["document_status"] == DocumentStatus.VALIDATED.value
        assert result["fields_disputed"] == 0
        assert field.resolved_value == "MARTEL"
        assert field.consensus_reached is True

    @pytest.mark.asyncio
    async def test_les_deux_divergent_le_champ_est_en_litige(self) -> None:
        """A deux voix, un desaccord ne peut pas se trancher.

        1 > 2/2 est faux : aucune valeur n'atteint la majorite stricte. Le champ
        part en DISPUTED et le document n'est pas valide — il attend un
        troisieme avis, cree par le routeur en etape CONSENSUS.
        """
        dataset, document = _dataset_and_document()
        field = _field_with_id(1)
        db = _db_for(
            dataset,
            document,
            submitted=2,
            fields=[field],
            proposals=[_proposal_for(1, "MARTEL"), _proposal_for(1, "MARTEI")],
        )

        result = await _resolve(1, 1, db)

        assert result["fields_disputed"] == 1
        assert field.status == DocumentFieldStatus.DISPUTED.value
        assert field.consensus_reached is False
        assert document.status != DocumentStatus.VALIDATED.value

    @pytest.mark.asyncio
    async def test_un_seul_soumis_le_consensus_attend(self) -> None:
        dataset, document = _dataset_and_document()
        db = AsyncMock()
        db.get = AsyncMock(side_effect=[dataset, document])
        submitted_result = MagicMock()
        submitted_result.scalar_one.return_value = 1
        db.execute = AsyncMock(return_value=submitted_result)

        result = await _resolve(1, 1, db)

        assert result["status"] == "waiting"
        assert result["submitted_jobs"] == 1
        assert result["required_operators"] == 2

    @pytest.mark.asyncio
    async def test_un_seul_des_deux_s_est_prononce_sur_le_champ(self) -> None:
        """Une seule proposition suffit a valider le champ.

        Les deux jobs sont soumis, mais un seul operateur a touche ce champ :
        la majorite se calcule sur les propositions recues, pas sur le nombre
        d'operateurs. Une voix sur une l'emporte donc.

        C'est coherent avec le champ que personne n'a touche, valide sur la
        valeur OCR : ne pas corriger vaut acceptation. Ce test est la pour que
        ce choix soit constate, et non subi.
        """
        dataset, document = _dataset_and_document()
        field = _field_with_id(1)
        db = _db_for(
            dataset,
            document,
            submitted=2,
            fields=[field],
            proposals=[_proposal_for(1, "MARTEL")],
        )

        result = await _resolve(1, 1, db)

        assert result["fields_disputed"] == 0
        assert field.resolved_value == "MARTEL"
        assert document.status == DocumentStatus.VALIDATED.value

    @pytest.mark.asyncio
    async def test_un_champ_en_litige_bloque_tout_le_document(self) -> None:
        """Le document n'est valide que si TOUS ses champs le sont."""
        dataset, document = _dataset_and_document()
        accorde = _field_with_id(1)
        litige = _field_with_id(2)
        db = _db_for(
            dataset,
            document,
            submitted=2,
            fields=[accorde, litige],
            proposals=[
                _proposal_for(1, "MARTEL"),
                _proposal_for(1, "MARTEL"),
                _proposal_for(2, "06013"),
                _proposal_for(2, "06015"),
            ],
        )

        result = await _resolve(1, 1, db)

        assert result["fields_total"] == 2
        assert result["fields_resolved"] == 1
        assert result["fields_disputed"] == 1
        assert accorde.status == DocumentFieldStatus.VALIDATED.value
        assert litige.status == DocumentFieldStatus.DISPUTED.value
        assert document.status != DocumentStatus.VALIDATED.value
