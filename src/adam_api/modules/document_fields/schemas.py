"""Schemas Pydantic du module document_fields.

DocumentFieldOut vient de adam_core.schemas.responses : il est deja utilise par
les endpoints de lecture existants, et en redefinir un ici ferait diverger deux
representations du meme objet.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from adam_core.enums.status import DocumentFieldStatus
from adam_core.schemas.responses import DocumentFieldOut


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
    """Tous les champs d'un schema, en une requete."""

    fields: List[DocumentFieldCreate] = Field(default_factory=list)


class DocumentFieldUpdate(BaseModel):
    """Mise a jour partielle : tout est optionnel."""

    group_id: Optional[str] = None
    ocr_value: Optional[str] = None
    resolved_value: Optional[str] = None
    status: Optional[str] = None
    ocr_confidence: Optional[float] = None
    ocr_polygon: Optional[List[float]] = None
    resolved_by: Optional[str] = None


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


__all__ = [
    "DocumentFieldBulkCreate",
    "DocumentFieldBulkOut",
    "DocumentFieldCreate",
    "DocumentFieldOut",
    "DocumentFieldUpdate",
    "SkippedFieldOut",
]
