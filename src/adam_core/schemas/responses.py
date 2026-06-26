"""Schemas Pydantic de reponse pour les endpoints Sprint 3. 

Chaque schema correspond a un type de retour d'endpoint.
``from_attributes=True`` permet de construire directement depuis un ORM row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Organisation
# ---------------------------------------------------------------------------

class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    schema_id: int
    name: str
    description: Optional[str] = None
    status: str
    ocr_provider: str
    required_operators: int
    ocr_job_enabled: bool


class DatasetStatsOut(BaseModel):
    dataset_id: int
    documents_total: int
    documents_validated: int


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------

class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    sha256_checksum: str
    file_size_bytes: int
    page_count: int
    mime_type: str
    storage_type: str


class FileRefOut(BaseModel):
    """Reference legere (id + chemin) utilisee dans les reponses Document."""

    id: int
    path: str


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class DocumentOut(BaseModel):
    """Reponse standard d'un document (liste / creation / patch).

    CA-2 : inclut page_count (issu du File associe) et image_paths
    (chemins des images de pages generees par le mini worker).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    file_id: int
    file_name: str
    status: str
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata_")
    # CA-2 : rempli par le mini worker une fois les images generees
    page_count: Optional[int] = None
    image_paths: Optional[List[str]] = None


class DocumentFullOut(BaseModel):
    """Reponse detaillee (GET /documents/{id}?view=full)."""

    id: int
    file_name: str
    status: str
    metadata: Optional[Dict[str, Any]] = None
    file: Optional[FileRefOut] = None
    pages: List[Dict[str, Any]] = Field(default_factory=list)
    ocr_results: List[Dict[str, Any]] = Field(default_factory=list)
    jobs: List[Dict[str, Any]] = Field(default_factory=list)
    page_count: Optional[int] = None
    image_paths: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# DocumentField
# ---------------------------------------------------------------------------

class DocumentFieldOut(BaseModel):
    """CA-3 : inclut ocr_polygon, statut et valeur resolue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    field_spec_id: int
    group_id: Optional[str] = None
    ocr_value: Optional[str] = None
    resolved_value: Optional[str] = None
    status: str
    ocr_confidence: Optional[float] = None
    consensus_reached: bool
    ocr_polygon: Optional[List[float]] = None


class DocumentFieldPatchOut(BaseModel):
    """Reponse d'un PATCH sur un champ."""

    id: int
    status: str
    resolved_value: Optional[str] = None


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    document_id: int
    agent_id: int
    state: str
    step: str
    started_at: datetime
    submitted_at: Optional[datetime] = None


class JobCreatedOut(BaseModel):
    """Reponse creation d'un job (POST /jobs)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    step: str
    state: str
    agent_id: int
    document_id: int
    dataset_id: int


class JobSubmitOut(BaseModel):
    """Reponse soumission d'un job (PATCH /jobs/{id}/submit)."""

    id: int
    state: str
    step: str
    submitted_at: Optional[datetime] = None


class FieldProposalOut(BaseModel):
    """Reponse creation / mise a jour d'une proposition (POST /jobs/{id}/propose)."""

    id: int
    job_id: int
    document_field_id: int
    step: str
    value: Optional[str] = None
    value_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Job detail (GET /jobs/{id}) — structure pages / sections
# ---------------------------------------------------------------------------

class JobFieldItemOut(BaseModel):
    id: int
    field_key: Optional[str] = None
    step: str
    value: Optional[str] = None
    value_type: Optional[str] = None
    reason: Optional[str] = None


class JobSectionOut(BaseModel):
    section_id: str
    section_label: Optional[str] = None
    fields: List[JobFieldItemOut] = Field(default_factory=list)


class JobPageOut(BaseModel):
    page: int
    sections: List[JobSectionOut] = Field(default_factory=list)


class JobDetailOut(BaseModel):
    """Reponse detaillee d'un job avec champs structures par page/section."""

    id: int
    step: str
    state: str
    agent_id: int
    document_id: int
    dataset_id: int
    started_at: datetime
    submitted_at: Optional[datetime] = None
    pages: List[JobPageOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ingestion (Sprint 3 - ticket 7)
# ---------------------------------------------------------------------------

class FileIngestionItemOut(BaseModel):
    """Resultat pour un fichier dans la reponse d'ingestion."""

    file_name: str
    status: str  # created | already_exists | rejected
    document_id: Optional[int] = None
    file_id: Optional[int] = None
    file_reused: Optional[bool] = None
    reason: Optional[str] = None


class IngestionOut(BaseModel):
    dataset_id: int
    received: int
    created: int
    already_exists: int
    rejected: int
    results: List[FileIngestionItemOut]
