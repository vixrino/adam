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


class DocumentFieldStatus(str, Enum):
    PENDING = "PENDING"
    CORRECTED = "CORRECTED"
    VALIDATED = "VALIDATED"
    DISPUTED = "DISPUTED"


class JobStep(str, Enum):
    VALIDATION = "VALIDATION"
    CORRECTION = "CORRECTION"
    CONSENSUS = "CONSENSUS"


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
