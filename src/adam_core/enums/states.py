"""Enumerations etats de job."""

from enum import Enum


class JobState(str, Enum):
    """Etat d'un job de labellisation."""

    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"
