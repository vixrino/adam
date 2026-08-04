"""Enumerations statuts metier."""

from enum import Enum


class OrganisationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DatasetStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DocumentStatus(str, Enum):
    RECEIVED = "RECEIVED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_CONSENSUS = "PENDING_CONSENSUS"
    VALIDATED = "VALIDATED"
    DISPUTED = "DISPUTED"
    EXPORTED = "EXPORTED"
    ARCHIVED = "ARCHIVED"


class DocumentStage(str, Enum):
    """Etape atteinte par un document dans la chaine de traitement.

    Distincte de DocumentStatus, qui est pilote par les routes et les workers de
    traitement. DocumentStage est un constat, derive de l'etat reel des tables
    liees : le fichier est-il la, les pages sont-elles rendues, l'OCR a-t-il
    produit un resultat, les champs sont-ils renseignes, le consensus est-il
    atteint. Rien ne l'ecrit a la main, DocumentProgressWorker le recalcule.

    Les valeurs sont ordonnees : une etape n'est atteinte que si la precedente
    l'est. INGESTED est le plancher, un document existant ayant toujours une
    ligne FILE.
    """

    INGESTED = "INGESTED"
    PAGES_RENDERED = "PAGES_RENDERED"
    OCR_AVAILABLE = "OCR_AVAILABLE"
    FIELDS_PREFILLED = "FIELDS_PREFILLED"
    ANNOTATION = "ANNOTATION"
    CONSENSUS_REACHED = "CONSENSUS_REACHED"


class DocumentFieldStatus(str, Enum):
    PENDING = "PENDING"
    CORRECTED = "CORRECTED"
    VALIDATED = "VALIDATED"
    DISPUTED = "DISPUTED"


class JobStep(str, Enum):
    VALIDATION = "VALIDATION"
    CORRECTION = "CORRECTION"
    CONSENSUS = "CONSENSUS"


class JobState(str, Enum):
    """Etat d'un job de labellisation."""

    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class ExportStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class FieldValueType(str, Enum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
