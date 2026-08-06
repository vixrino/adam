"""Ecriture des DOCUMENT_FIELD : creation unitaire, creation en lot, suppression.

La lecture (`GET /documents/{id}/fields`) et la mise a jour partielle
(`PATCH /documents/{id}/fields/{field_id}`) restent dans routers/documents.py,
ou elles existaient deja. Ce module ajoute ce qui manquait, sans deplacer
l'existant : un renommage de route casserait les appelants pour un gain nul.

Le prefixe est le meme que celui de documents.py, les deux routeurs se partagent
donc l'espace /documents. C'est voulu : du point de vue de l'appelant, les
champs d'un document sont une sous-ressource du document, quel que soit le
fichier ou le code vit.

Pourquoi passer par HTTP plutot que par l'ORM
----------------------------------------------
PrepopulationWorker pourrait ecrire directement en base. Le faire passer par ces
endpoints centralise ici la coherence field_spec/schema et la contrainte
d'unicite, au lieu de les dupliquer dans chaque service qui creerait des champs.
"""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_api.services import document_fields as service
from adam_core.enums.status import DocumentFieldStatus
from adam_core.models import Document, DocumentField
from adam_core.schemas.responses import DocumentFieldOut
from adam_core.utils.exceptions import raise_conflict, raise_not_found, raise_unprocessable

router = APIRouter(prefix="/documents", tags=["DocumentFields"])


class DocumentFieldCreate(BaseModel):
    """Un champ a creer.

    resolved_by est accepte mais ignore si resolved_value est absent : le
    service refuse de designer un resolveur pour une valeur qui n'existe pas.
    """

    field_spec_id: int
    group_id: Optional[str] = None
    ocr_value: Optional[str] = None
    resolved_value: Optional[str] = None
    status: str = DocumentFieldStatus.PENDING.value
    ocr_confidence: Optional[float] = None
    ocr_polygon: Optional[List[float]] = None
    resolved_by: Optional[str] = None


class DocumentFieldBulkCreate(BaseModel):
    fields: List[DocumentFieldCreate] = Field(default_factory=list)


class SkippedFieldOut(BaseModel):
    """Champ ignore par le lot parce qu'il existait deja."""

    field_spec_id: int
    group_id: Optional[str] = None


class DocumentFieldBulkOut(BaseModel):
    """Reponse du lot : ce qui a ete cree, ce qui existait deja.

    Distinguer les deux permet a l'appelant de rejouer un document sans se
    demander si son retry a duplique quoi que ce soit.
    """

    document_id: int
    created: List[DocumentFieldOut] = Field(default_factory=list)
    skipped: List[SkippedFieldOut] = Field(default_factory=list)


async def _load_document(db: AsyncSession, document_id: int) -> Document:
    document = await service.get_document_or_none(db, document_id)
    if document is None:
        raise_not_found(Document)
    return document


def _to_out(row: DocumentField, value_type: Optional[str] = None) -> DocumentFieldOut:
    return DocumentFieldOut(
        id=row.id,
        document_id=row.document_id,
        field_spec_id=row.field_spec_id,
        group_id=row.group_id,
        value_type=value_type,
        ocr_value=row.ocr_value,
        resolved_value=row.resolved_value,
        status=row.status,
        ocr_confidence=row.ocr_confidence,
        consensus_reached=row.consensus_reached,
        ocr_polygon=row.ocr_polygon,
    )


@router.post("/{document_id}/fields", response_model=DocumentFieldOut, status_code=201)
async def create_document_field(
    document_id: int,
    body: DocumentFieldCreate,
    db: AsyncSession = Depends(get_db),
) -> DocumentFieldOut:
    """Cree un champ unique. 409 si le triplet existe deja, 422 s'il est hors schema."""
    document = await _load_document(db, document_id)
    try:
        row = await service.create_one(db, document, body.model_dump())
    except service.FieldSpecMismatch as exc:
        raise_unprocessable(str(exc))
    except service.DuplicateField as exc:
        raise_conflict(DocumentField, str(exc))
    return _to_out(row)


@router.post("/{document_id}/fields/bulk", response_model=DocumentFieldBulkOut, status_code=201)
async def create_document_fields_bulk(
    document_id: int,
    body: DocumentFieldBulkCreate,
    db: AsyncSession = Depends(get_db),
) -> DocumentFieldBulkOut:
    """Cree tous les champs d'un schema en une requete.

    Idempotent : un second appel sur les memes champs ne cree pas de doublon et
    ne leve pas. C'est ce qui permet a PrepopulationWorker de reprendre un
    document interrompu sans etat intermediaire a nettoyer.

    Un field_spec_id hors schema rejette le lot entier en 422, pour ne pas
    laisser un document a moitie pre-alimente.
    """
    document = await _load_document(db, document_id)
    payloads = [item.model_dump() for item in body.fields]
    try:
        outcome = await service.create_bulk(db, document, payloads)
    except service.FieldSpecMismatch as exc:
        raise_unprocessable(str(exc))
    return DocumentFieldBulkOut(
        document_id=document_id,
        created=[_to_out(row) for row in outcome.created],
        skipped=[
            SkippedFieldOut(field_spec_id=spec_id, group_id=group_id)
            for spec_id, group_id in outcome.skipped
        ],
    )


@router.delete("/{document_id}/fields/{field_id}", status_code=204)
async def delete_document_field(
    document_id: int,
    field_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime un champ. Pas de soft delete, comme les autres suppressions."""
    row: Any = await db.get(DocumentField, field_id)
    if row is None or row.document_id != document_id:
        raise_not_found(DocumentField)
    await db.delete(row)
