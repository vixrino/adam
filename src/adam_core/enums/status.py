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


class TestRecipeStatus(str, Enum):
    """Cycle de vie d'une recette de test OCR.

    DRAFT accepte les modifications ; LOCKED fige le perimetre, prerequis de
    toute execution — deux passages ne sont comparables que si la recette n'a
    pas bouge entre eux ; ARCHIVED la retire des listes sans casser l'historique
    des executions qui la referencent.
    """

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
    """Nature d'un ecart entre la sortie OCR et la verite terrain.

    MISSING : la verite porte une valeur, le moteur n'a rien rendu.
    WRONG   : le moteur a rendu autre chose que la verite.

    Pas de verdict UNEXPECTED au niveau ligne : un champ lu hors schema n'a pas
    de document_field a referencer. Ces cas sont comptes sur l'execution
    (unexpected_count), ou l'information agregee suffit au diagnostic.
    """

    MISSING = "MISSING"
    WRONG = "WRONG"


class ComparisonDiffKind(str, Enum):
    """Categorie d'un ecart WRONG, sans reveler la valeur.

    C'est le diagnostic publiable pour les champs sensibles : « 40 % des ecarts
    de bien.valeur sont des DIGIT » suffit a conclure que le moteur lit mal les
    chiffres, sans stocker un IBAN.
    """

    CASE = "CASE"
    WHITESPACE = "WHITESPACE"
    DIGIT = "DIGIT"
    FORMAT = "FORMAT"
    TOTAL = "TOTAL"
