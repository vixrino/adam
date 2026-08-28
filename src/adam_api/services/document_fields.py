"""Regles metier de creation des DOCUMENT_FIELD.

Ce service existe parce que la creation des champs passe par HTTP et non par un
acces ORM direct depuis le worker : la validation de coherence entre field_spec
et schema, et la gestion de la contrainte d'unicite, vivent ici une seule fois
plutot que dupliquees dans chaque appelant.

Deux entrees, la creation unitaire et la creation en lot, qui ne se comportent
pas pareil face a un conflit. L'unitaire echoue en 409, l'appelant sachant ce
qu'il demande. Le lot, lui, ignore les champs deja presents et les rapporte :
c'est ce qui rend le worker rejouable apres un crash au milieu d'un document,
sans quoi la reprise echouerait sur le premier champ deja cree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.exceptions.document_fields import DuplicateField, FieldSpecMismatch
from adam_core.enums.status import DocumentFieldStatus
from adam_core.models import Dataset, DocSchema, Document, DocumentField, FieldSpec


@dataclass
class BulkOutcome:
    """Resultat d'une creation en lot."""

    created: List[DocumentField] = field(default_factory=list)
    skipped: List[Tuple[int, Optional[str]]] = field(default_factory=list)


async def resolve_schema_id(db: AsyncSession, document: Document) -> int:
    """Schema attendu pour ce document, via son dataset."""
    schema_id = (
        await db.execute(select(Dataset.schema_id).where(Dataset.id == document.dataset_id))
    ).scalar_one_or_none()
    if schema_id is None:
        raise FieldSpecMismatch([], -1)
    return int(schema_id)


async def _valid_field_spec_ids(db: AsyncSession, schema_id: int) -> Set[int]:
    rows = (
        (await db.execute(select(FieldSpec.id).where(FieldSpec.schema_id == schema_id)))
        .scalars()
        .all()
    )
    return set(rows)


async def _existing_keys(db: AsyncSession, document_id: int) -> Set[Tuple[int, Optional[str]]]:
    """Triplets deja presents, sous la forme (field_spec_id, group_id)."""
    rows = (
        await db.execute(
            select(DocumentField.field_spec_id, DocumentField.group_id).where(
                DocumentField.document_id == document_id
            )
        )
    ).all()
    return {(row.field_spec_id, row.group_id) for row in rows}


def _build(document_id: int, payload: Dict[str, Any]) -> DocumentField:
    """Construit la ligne, en appliquant les defauts metier.

    resolved_by n'est pose que si une valeur resolue existe : un champ sans
    valeur n'a pas de resolveur, et marquer "ocr_system" sur un champ vide
    laisserait croire que l'OCR l'a traite alors qu'il ne l'a pas trouve.
    """
    resolved_value = payload.get("resolved_value")
    resolved_by = payload.get("resolved_by") if resolved_value is not None else None
    return DocumentField(
        document_id=document_id,
        field_spec_id=payload["field_spec_id"],
        group_id=payload.get("group_id"),
        ocr_value=payload.get("ocr_value"),
        resolved_value=resolved_value,
        status=payload.get("status") or DocumentFieldStatus.PENDING.value,
        ocr_confidence=payload.get("ocr_confidence"),
        ocr_polygon=payload.get("ocr_polygon"),
        resolved_by=resolved_by,
    )


async def create_one(
    db: AsyncSession, document: Document, payload: Dict[str, Any]
) -> DocumentField:
    """Cree un champ unique. Leve DuplicateField si le triplet existe deja."""
    schema_id = await resolve_schema_id(db, document)
    valid_ids = await _valid_field_spec_ids(db, schema_id)
    if payload["field_spec_id"] not in valid_ids:
        raise FieldSpecMismatch([payload["field_spec_id"]], schema_id)

    key = (payload["field_spec_id"], payload.get("group_id"))
    if key in await _existing_keys(db, document.id):
        raise DuplicateField(*key)

    row = _build(document.id, payload)
    db.add(row)
    await db.flush()
    return row


async def create_bulk(
    db: AsyncSession, document: Document, payloads: Sequence[Dict[str, Any]]
) -> BulkOutcome:
    """Cree tous les champs d'un schema en une passe, en ignorant les doublons.

    La validation des field_spec_id est faite d'un bloc avant toute insertion :
    un lot incoherent est rejete entierement, pour ne pas laisser un document a
    moitie pre-alimente avec un 422 en retour.

    Les doublons internes au lot sont traites comme des doublons vis-a-vis de la
    base : le premier passe, les suivants sont rapportes en skipped.
    """
    schema_id = await resolve_schema_id(db, document)
    valid_ids = await _valid_field_spec_ids(db, schema_id)
    unknown = sorted({p["field_spec_id"] for p in payloads} - valid_ids)
    if unknown:
        raise FieldSpecMismatch(unknown, schema_id)

    seen = await _existing_keys(db, document.id)
    outcome = BulkOutcome()
    for payload in payloads:
        key = (payload["field_spec_id"], payload.get("group_id"))
        if key in seen:
            outcome.skipped.append(key)
            continue
        seen.add(key)
        row = _build(document.id, payload)
        db.add(row)
        outcome.created.append(row)

    if outcome.created:
        await db.flush()
    return outcome


async def get_document_or_none(db: AsyncSession, document_id: int) -> Optional[Document]:
    return await db.get(Document, document_id)


async def schema_of_document(db: AsyncSession, document: Document) -> Optional[DocSchema]:
    """Schema complet du document, pour les appelants qui en ont besoin."""
    schema_id = await resolve_schema_id(db, document)
    return await db.get(DocSchema, schema_id)
