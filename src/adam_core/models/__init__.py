"""Import de tous les modeles (requis pour Alembic)."""

from adam_core.models.comparison_result import ComparisonResult
from adam_core.models.dataset import Dataset
from adam_core.models.doc_schema import DocSchema
from adam_core.models.document import Document
from adam_core.models.document_field import DocumentField
from adam_core.models.evaluation_report import EvaluationReport
from adam_core.models.document_progress import DocumentProgress
from adam_core.models.field_proposal import FieldProposal
from adam_core.models.field_spec import FieldSpec
from adam_core.models.file import File
from adam_core.models.job import Job
from adam_core.models.test_execution import TestExecution
from adam_core.models.test_recipe import TestRecipe
from adam_core.models.ocr_result import OcrResult
from adam_core.models.organisation import Organisation
from adam_core.models.project import Project
from adam_core.models.user import User
from adam_core.models.user_project import UserProject

__all__ = [
    "ComparisonResult",
    "EvaluationReport",
    "TestExecution",
    "TestRecipe",
    "Dataset",
    "DocSchema",
    "Document",
    "DocumentField",
    "DocumentProgress",
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
