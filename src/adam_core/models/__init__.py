"""Import de tous les modeles (requis pour Alembic)."""

from adam_core.models.dataset import Dataset
from adam_core.models.doc_schema import DocSchema
from adam_core.models.document import Document
from adam_core.models.document_field import DocumentField
from adam_core.models.field_proposal import FieldProposal
from adam_core.models.field_spec import FieldSpec
from adam_core.models.file import File
from adam_core.models.job import Job
from adam_core.models.ocr_result import OcrResult
from adam_core.models.organisation import Organisation
from adam_core.models.project import Project
from adam_core.models.user import User
from adam_core.models.user_project import UserProject

__all__ = [
    "Dataset",
    "DocSchema",
    "Document",
    "DocumentField",
    "FieldProposal",
    "FieldSpec",
    "File",
    "Job",
    "OcrResult",
    "Organisation",
    "Project",
    "User",
    "UserProject",
]
