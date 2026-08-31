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
    ERROR = "ERROR"  # rendu impossible (PDF illisible) : sort le doc de la file de traitement


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
