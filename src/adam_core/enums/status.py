"""
Énumérations métier liées aux statuts de cycle de vie.
"""

from enum import Enum


class DocumentStatus(str, Enum):
    """Avancement d'un DOCUMENT dans le pipeline de labellisation."""

    RECEIVED = "RECEIVED"
    INGESTED = "INGESTED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_CONSENSUS = "PENDING_CONSENSUS"
    VALIDATED = "VALIDATED"
    EXPORTED = "EXPORTED"
    ERROR = "ERROR"


class JobStep(str, Enum):
    """Étape du workflow de labellisation pour un JOB."""

    VALIDATION = "VALIDATION"
    CONSENSUS = "CONSENSUS"


class JobState(str, Enum):
    """État courant d'un JOB."""

    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


class DocumentFieldStatus(str, Enum):
    """État d'un DOCUMENT_FIELD après révision humaine."""

    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    CORRECTED = "CORRECTED"
    DISPUTED = "DISPUTED"


class DatasetStatus(str, Enum):
    """Cycle de vie d'un DATASET."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    EXPORTED = "EXPORTED"


class ProjectStatus(str, Enum):
    """Cycle de vie d'un PROJECT."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    SUSPENDED = "SUSPENDED"


class UserStatus(str, Enum):
    """Cycle de vie d'un compte USER."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class ExportStatus(str, Enum):
    """État d'un export DATASET_EXPORT."""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class FieldValueType(str, Enum):
    """
    Types de valeur d'un champ (KVPair).
    """

    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"


class TestRecipeStatus(str, Enum):
    """Cycle de vie d'une recette de test OCR."""

    __test__ = False  # pytest tenterait de collecter la classe (prefixe Test*)

    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    ARCHIVED = "ARCHIVED"


class TestExecutionStatus(str, Enum):
    """Cycle de vie d'une execution de recette."""

    __test__ = False  # meme raison

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ComparisonVerdict(str, Enum):
    """Nature d'un ecart entre la sortie OCR et la verite terrain."""

    MISSING = "MISSING"
    WRONG = "WRONG"


class ComparisonDiffKind(str, Enum):
    """Categorie d'un ecart WRONG, sans reveler la valeur."""

    CASE = "CASE"
    WHITESPACE = "WHITESPACE"
    DIGIT = "DIGIT"
    FORMAT = "FORMAT"
    TOTAL = "TOTAL"
