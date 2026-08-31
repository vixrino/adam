"""Routes d'ecriture des DOCUMENT_FIELD.

Le routeur ne porte aucune regle : il charge le document, delegue au service, et
traduit ses erreurs en codes HTTP. Toute la coherence metier vit dans service.py,
ce qui la rend testable sans requete et reutilisable hors contexte HTTP.

La lecture (`GET /documents/{id}/fields`) et la mise a jour partielle
(`PATCH /documents/{id}/fields/{field_id}`) restent dans routers/documents.py,
ou elles existaient deja. Ce module ajoute ce qui manquait sans deplacer
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

from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_api.exceptions.document_fields import DuplicateField, FieldSpecMismatch
from adam_api.schemas.document_fields import (
    DocumentFieldBulkCreate,
    DocumentFieldBulkOut,
    DocumentFieldCreate,
    DocumentFieldOut,
    SkippedFieldOut,
)
from adam_api.services import document_fields as service
from adam_core.models import Document, DocumentField
from adam_core.utils.exceptions import raise_conflict, raise_not_found, raise_unprocessable

router = APIRouter(prefix="/documents", tags=["DocumentFields"])


async def _load_document(db: AsyncSession, document_id: int) -> Document:
    document = await service.get_document_or_none(db, document_id)
    if document is None:
        raise_not_found(Document)
    return document


def _to_out(row: DocumentField) -> DocumentFieldOut:
    """Serialise une ligne fraichement creee.

    value_type n'est pas renseigne : il se lit sur le FieldSpec, que la creation
    n'a pas charge, et le remplir couterait une requete par champ pour une
    information dont l'appelant dispose deja — c'est lui qui a fourni les
    field_spec_id. Les endpoints de lecture, eux, le portent, ayant deja la
    jointure.
    """
    return DocumentFieldOut(
        id=row.id,
        document_id=row.document_id,
        field_spec_id=row.field_spec_id,
        group_id=row.group_id,
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
    except FieldSpecMismatch as exc:
        raise_unprocessable(str(exc))
    except DuplicateField as exc:
        raise_conflict(DocumentField, str(exc))
    return _to_out(row)


@router.post(
    "/{document_id}/fields/bulk",
    response_model=DocumentFieldBulkOut,
    status_code=201,
    responses={200: {"description": "Aucun champ cree : tous existaient deja"}},
)
async def create_document_fields_bulk(
    document_id: int,
    body: DocumentFieldBulkCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> DocumentFieldBulkOut:
    """Cree tous les champs d'un schema en une requete.

    Idempotent : un second appel sur les memes champs ne cree pas de doublon et
    ne leve pas. C'est ce qui permet a PrepopulationWorker de reprendre un
    document interrompu sans etat intermediaire a nettoyer.

    Un field_spec_id hors schema rejette le lot entier en 422, pour ne pas
    laisser un document a moitie pre-alimente.

    201 quand au moins un champ est cree, 200 sinon. Un rejeu integral annoncant
    Created, alors qu'il n'a rien cree, dit le contraire de ce que porte son
    corps de reponse ; la difference se lit dans un onglet reseau ou un journal
    d'acces, la ou personne n'ouvrira le corps.
    """
    document = await _load_document(db, document_id)
    payloads = [item.model_dump() for item in body.fields]
    try:
        outcome = await service.create_bulk(db, document, payloads)
    except FieldSpecMismatch as exc:
        raise_unprocessable(str(exc))
    if not outcome.created:
        response.status_code = 200
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
