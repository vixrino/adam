"""Schemas Pydantic de reponse pour les endpoints Sprint 3. 

Chaque schema correspond a un type de retour d'endpoint.
``from_attributes=True`` permet de construire directement depuis un ORM row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Organisation
# ---------------------------------------------------------------------------

class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


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
    created_at: datetime


class FileDetailOut(BaseModel):
    """Reponse GET /files/{id} — inclut le nombre de documents references."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    sha256_checksum: str
    file_size_bytes: int
    page_count: int
    mime_type: str
    storage_type: str
    created_at: datetime
    documents_count: int


class FileCreatedOut(BaseModel):
    """Reponse POST /files — indique si le fichier est une deduplication."""

    id: int
    file_path: str
    sha256_checksum: str
    deduplicated: bool


class FilePatchOut(BaseModel):
    """Reponse PATCH /files/{id} — seuls les champs mutables sont retournes."""

    id: int
    file_path: str
    page_count: int


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
    updated_at: datetime


class DocumentFieldInPageOut(BaseModel):
    """Champ tel qu'affiché dans la vue full d'un document."""

    id: int
    field_key: Optional[str] = None
    ocr_value: Optional[str] = None
    resolved_value: Optional[str] = None
    status: str


class DocumentSectionOut(BaseModel):
    """Section dans une page (vue full document)."""

    id: str
    fields: List[DocumentFieldInPageOut] = Field(default_factory=list)


class DocumentPageOut(BaseModel):
    """Page d'un document (vue full)."""

    page_number: int
    sections: List[DocumentSectionOut] = Field(default_factory=list)


class DocumentOcrResultOut(BaseModel):
    """Référence légère vers un OcrResult dans la vue full document."""

    id: int


class DocumentJobOut(BaseModel):
    """Référence légère vers un Job dans la vue full document."""

    id: int
    state: str


class DocumentFullOut(BaseModel):
    """Reponse detaillee (GET /documents/{id}?view=full)."""

    id: int
    file_name: str
    status: str
    metadata: Optional[Dict[str, Any]] = None
    file: Optional[FileRefOut] = None
    pages: List[DocumentPageOut] = Field(default_factory=list)
    ocr_results: List[DocumentOcrResultOut] = Field(default_factory=list)
    jobs: List[DocumentJobOut] = Field(default_factory=list)
    page_count: Optional[int] = None
    image_paths: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# DocumentField by-section
# ---------------------------------------------------------------------------

class FieldBySectionItemOut(BaseModel):
    """Champ minimal dans la réponse par section."""

    id: int
    field_key: Optional[str] = None


class DocumentFieldsBySectionOut(BaseModel):
    """Reponse GET /documents/{id}/fields/by-section."""

    document_id: int
    sections: Dict[str, List[FieldBySectionItemOut]]


# ---------------------------------------------------------------------------
# DocumentField
# ---------------------------------------------------------------------------

class DocumentFieldOut(BaseModel):
    """CA-3 : inclut ocr_polygon, statut et valeur resolue.

    ocr_value et resolved_value sont exposees dans leur type natif JSON
    (bool, int, float ou str) selon value_type, via parse_field_value.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    field_spec_id: int
    group_id: Optional[str] = None
    value_type: Optional[str] = None
    ocr_value: Optional[Any] = None
    resolved_value: Optional[Any] = None
    status: str
    ocr_confidence: Optional[float] = None
    consensus_reached: bool
    ocr_polygon: Optional[List[float]] = None

    @model_validator(mode="after")
    def _parse_values(self) -> "DocumentFieldOut":
        from adam_core.utils.field_parser import parse_field_value
        self.ocr_value = parse_field_value(self.ocr_value, self.value_type)
        self.resolved_value = parse_field_value(self.resolved_value, self.value_type)
        return self


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
    started_at: Optional[datetime] = None
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
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    pages: List[JobPageOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ingestion (Sprint 3 - ticket 7)
# ---------------------------------------------------------------------------

class FileIngestionItemOut(BaseModel):
    """Resultat pour un fichier dans la reponse d'ingestion."""

    file_name: str
    status: str  # created | created_file_reused | already_exists | rejected
    document_id: Optional[int] = None
    file_id: Optional[int] = None
    file_path: Optional[str] = None  # a titre de debug
    reason: Optional[str] = None


class IngestionOut(BaseModel):
    dataset_id: int
    received: int
    created: int
    already_exists: int
    rejected: int
    results: List[FileIngestionItemOut]


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

class OcrResultOut(BaseModel):
    id: int
    document_id: int
    dataset_id: int
    storage_mode: str
    processed_at: Optional[datetime] = None


class OcrResultDetailOut(BaseModel):
    id: int
    document_id: int
    dataset_id: int
    storage_mode: str
    processed_at: Optional[datetime] = None
    raw_json: Optional[Dict[str, Any]] = None


class OcrResultCreatedOut(BaseModel):
    ocr_result_id: int
    document_fields_created: int
    document_fields_skipped: int
    document_status: str


# ---------------------------------------------------------------------------
# Organisation (extensions)
# ---------------------------------------------------------------------------

class UserProjectRefOut(BaseModel):
    project_id: int
    role: str


class OrgUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    matricule: str
    status: str
    projects: List[UserProjectRefOut] = []


class OrganisationPatchOut(BaseModel):
    id: int
    name: str


class OrganisationArchiveOut(BaseModel):
    id: int
    archived: bool


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class ProjectOut(BaseModel):
    id: int
    name: str
    organisation_id: int


class ProjectDetailOut(BaseModel):
    id: int
    name: str
    status: str
    updated_at: Optional[datetime] = None


class ProjectCreatedOut(BaseModel):
    id: int
    name: str


class UserProjectOut(BaseModel):
    user_id: int
    project_id: int
    role: str


class UserRolePatchOut(BaseModel):
    user_id: int
    project_id: int
    role: str
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# DocSchema
# ---------------------------------------------------------------------------

class SchemaListItemOut(BaseModel):
    id: int
    name: str
    document_type: str
    version: int
    project_id: int
    created_at: Optional[datetime] = None


class FieldSpecItemOut(BaseModel):
    id: int
    page: int
    section_id: str
    section_label: str
    field_key: str
    display_label: str
    value_type: str
    required: bool
    display_order: int
    group_id: Optional[str] = None
    polygon: Optional[List[float]] = None
    updated_at: Optional[datetime] = None


class FieldSpecDetailOut(BaseModel):
    id: int
    schema_id: int
    page: int
    section_id: str
    section_label: str
    field_key: str
    display_label: str
    value_type: str
    required: bool
    display_order: int
    group_id: Optional[str] = None
    polygon: Optional[List[float]] = None
    updated_at: Optional[datetime] = None


class FieldSpecCreatedOut(BaseModel):
    id: int
    field_key: str
    schema_id: int


class SchemaDetailOut(BaseModel):
    id: int
    name: str
    document_type: str
    version: int
    project_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    field_specs: List[FieldSpecItemOut] = []


class SchemaCreatedOut(BaseModel):
    id: int
    name: str
    document_type: str
    version: int
    field_specs_created: int = 0


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserListItemOut(BaseModel):
    id: int
    email: str
    full_name: str
    matricule: str
    status: str
    organisation_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class UserProjectDetailOut(BaseModel):
    project_id: int
    role: str
    created_at: Optional[datetime] = None


class UserDetailOut(BaseModel):
    id: int
    email: str
    full_name: str
    matricule: str
    status: str
    organisation_id: int
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    projects: List[UserProjectDetailOut] = []


class UserCreatedOut(BaseModel):
    id: int
    email: str
    full_name: str
    matricule: str
    status: str


class UserPatchOut(BaseModel):
    id: int
    email: str
    full_name: str
    matricule: str
    status: str
    organisation_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
