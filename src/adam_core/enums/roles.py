"""Enumerations roles utilisateur."""

from enum import Enum


class UserRole(str, Enum):
    """Role d'un utilisateur dans un projet."""

    OPERATOR = "OPERATOR"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


class ExportFormat(str, Enum):
    """Format d'export dataset."""

    JSON = "JSON"
    CSV = "CSV"
    PDF = "PDF"
