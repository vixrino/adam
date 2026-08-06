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
    """Etapes du pipeline documentaire, dans l'ordre de progression.

    INGESTED s'intercale entre RECEIVED et IN_PROGRESS : il marque le moment ou
    les images du document ont ete generees et ou la pre-alimentation OCR peut
    commencer. C'est la file d'attente de PrepopulationWorker, qui n'a aucun
    moyen de distinguer un document tout juste recu d'un document dont les
    pages sont pretes si les deux portent RECEIVED.

    ERROR sort un document de la chaine plutot que de le laisser dans un statut
    qui le ferait repoller indefiniment.
    """

    RECEIVED = "RECEIVED"
    INGESTED = "INGESTED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_CONSENSUS = "PENDING_CONSENSUS"
    VALIDATED = "VALIDATED"
    DISPUTED = "DISPUTED"
    EXPORTED = "EXPORTED"
    ARCHIVED = "ARCHIVED"
    ERROR = "ERROR"


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
