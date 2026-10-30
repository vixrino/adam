"""
Import de tous les modèles ORM.

!! CRITIQUE pour create_all() et Alembic autogenerate :
    chaque modèle doit être importé ici pour être enregistré
    dans Base.metadata avant l'appel à create_all().
"""

# Module 3 : Dataset et Documents
from adam_core.models.comparison_result import ComparisonResult
from adam_core.models.dataset import Dataset
from adam_core.models.doc_schema import DocSchema
from adam_core.models.document import Document
from adam_core.models.document_field import DocumentField
from adam_core.models.evaluation_report import EvaluationReport
from adam_core.models.field_proposal import FieldProposal
from adam_core.models.field_spec import FieldSpec
from adam_core.models.file import File

# Module 4 : Workflow Labellisation
from adam_core.models.job import Job
from adam_core.models.ocr_result import OcrResult

# Module 1 : Management
from adam_core.models.organisation import Organisation

# Module 2 : Projet et Schéma
from adam_core.models.project import Project
from adam_core.models.schema_page import SchemaPage
from adam_core.models.test_execution import TestExecution
from adam_core.models.test_recipe import TestRecipe
from adam_core.models.user import User
from adam_core.models.user_project import UserProject  # conservé : porte le rôle

__all__ = [
    "ComparisonResult",
    "EvaluationReport",
    "TestExecution",
    "TestRecipe",
    "Organisation",
    "User",
    "UserProject",
    "Project",
    "SchemaPage",
    "DocSchema",
    "FieldSpec",
    "Dataset",
    "File",
    "Document",
    "OcrResult",
    "DocumentField",
    "Job",
    "FieldProposal",
]
