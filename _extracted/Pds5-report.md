I'll start by listing the Pds5 screenshots and converting the PDF if any pages are missing.

[REDACTED]
Only 3 pages exist — converting the full PDF to PNG next.

[REDACTED]
All 27 pages are ready — reading the screenshots in batches to transcribe the code.

[REDACTED]
[REDACTED]
[REDACTED]
Checking for an existing adam project to cross-reference.

[REDACTED]
[REDACTED]
# Pds5 Screenshot Transcription Report — adam (27 pages)

**Source:** lot PDF transcrit *(fichiers supprimés — anonymisation)*  
**Repo:** `git.example.com/example-org/adam/adam` (branch `develop`)

---

## Summary by page type

| Pages | Type | Content |
|-------|------|---------|
| 01–04 | **Code** | `src/adam_api/services/consensus.py` (lines 36–155) |
| 05–12 | **Docs** | `src/adam_core/README.md` (directory listing + full README) |
| 13 | **Dir listing** | `src/` |
| 14–16 | **Code** | `src/adam_worker/src/consensus_worker.py` |
| 17–19 | **Code** | `src/adam_core/core/config.py` |
| 20–21 | **Dir listing** | `src/adam_core/db/` + empty `__init__.py` |
| 22–24 | **Code** | `src/adam_core/db/base.py`, `session.py` |
| 25–26 | **Dir listing** | `src/adam_core/enums/` + empty `__init__.py` |
| 27 | **Code** | `src/adam_core/enums/ocr.py` |

---

## Page-by-page report

---

### Page 01 — `src/adam_api/services/consensus.py` (lines 36–75)

```python
        Déclenchement : background task depuis submit_job.
        """
        try:
            async with get_async_session() as db:
                return await _resolve(document_id, dataset_id, db)
        except Exception:
            logger.exception(
                "try_resolve echoue [document_id=%s dataset_id=%s]",
                document_id,
                dataset_id,
            )
            return {"error": "try_resolve echoue", "document_id": document_id}

def _apply_vote(df: DocumentField, field_proposals: list[FieldProposal]) -> bool:
    """Applique le vote majoritaire. Retourne True si consensus, False si dispute."""
    if not field_proposals:
        df.consensus_reached = True
        df.resolved_value = df.ocr_value
        df.status = DocumentFieldStatus.VALIDATED.value
        return True

    values = [p.value for p in field_proposals]
    top_value, top_count = Counter(values).most_common(1)[0]

    if top_count > len(values) / 2:
        df.consensus_reached = True
        df.resolved_value = top_value
        df.status = DocumentFieldStatus.VALIDATED.value
        return True

    df.consensus_reached = False
    df.status = DocumentFieldStatus.DISPUTED.value
    return False

async def _resolve(document_id: int, dataset_id: int, db: AsyncSession) -> dict[str, Any]:
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
```

> **Note:** Lines 1–35 not visible in Pds5 (start of `try_resolve` function signature/imports missing).

---

### Page 02 — `src/adam_api/services/consensus.py` (lines 74–112)

```python
    if not dataset:
        logger.error("try_resolve: dataset introuvable [dataset_id=%s]", dataset_id)
        return {"document_id": document_id, "status": "error", "reason": "dataset introuvable"}

    document = await db.get(Document, document_id)
    if not document:
        logger.error("try_resolve: document introuvable [document_id=%s]", document_id)
        return {"document_id": document_id, "status": "error", "reason": "document introuvable"}

    if document.status == DocumentStatus.VALIDATED.value:
        logger.debug("try_resolve: document déjà validé [document_id=%s]", document_id)
        return {"document_id": document_id, "status": "already_validated"}

    submitted_count: int = (
        await db.execute(
            select(count(Job.id))
            .where(Job.document_id == document_id)
            .where(Job.state == JobState.SUBMITTED.value)
        )
    ).scalar_one()

    if submitted_count < dataset.required_operators:
        logger.debug(
            "try_resolve: attente [document_id=%s jobs=%s/%s]",
            document_id,
            submitted_count,
            dataset.required_operators,
        )
        return {
            "document_id": document_id,
            "status": "waiting",
            "submitted_jobs": submitted_count,
            "required_operators": dataset.required_operators,
        }

    fields = (
        await db.execute(select(DocumentField).where(DocumentField.document_id == document_id))
        .scalars()
        .all()
```

---

### Page 03 — `src/adam_api/services/consensus.py` (lines 110–147)

```python
        (await db.execute(select(DocumentField).where(DocumentField.document_id == document_id)))
        .scalars()
        .all()
    )

    proposals = (
        (
            await db.execute(
                select(FieldProposal)
                .join(Job, FieldProposal.job_id == Job.id)
                .where(Job.document_id == document_id)
                .where(Job.state == JobState.SUBMITTED.value)
            )
        )
        .scalars()
        .all()
    )

    by_field: dict[int, list[FieldProposal]] = {}
    for p in proposals:
        by_field.setdefault(p.document_field_id, []).append(p)

    all_resolved = all(_apply_vote(df, by_field.get(df.id, [])) for df in fields)

    if all_resolved:
        document.status = DocumentStatus.VALIDATED.value
        logger.info("document valide [document_id=%s]", document_id)
    else:
        disputed = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
        logger.info(
            "consensus partiel [document_id=%s disputed=%s/%s]",
            document_id,
            disputed,
            len(fields),
        )

    disputed_count = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
    return {
```

---

### Page 04 — `src/adam_api/services/consensus.py` (lines 122–155)

```python
        )
        .scalars()
        .all()
    )

    by_field: dict[int, list[FieldProposal]] = {}
    for p in proposals:
        by_field.setdefault(p.document_field_id, []).append(p)

    all_resolved = all(_apply_vote(df, by_field.get(df.id, [])) for df in fields)

    if all_resolved:
        document.status = DocumentStatus.VALIDATED.value
        logger.info("document valide [document_id=%s]", document_id)
    else:
        disputed = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
        logger.info(
            "consensus partiel [document_id=%s disputed=%s/%s]",
            document_id,
            disputed,
            len(fields),
        )

    disputed_count = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
    return {
        "document_id": document_id,
        "document_status": document.status,
        "fields_total": len(fields),
        "fields_resolved": len(fields) - disputed_count,
        "fields_disputed": disputed_count,
        "submitted_jobs": submitted_count,
    }
```

---

### Page 05 — Directory listing: `src/adam_core/`

| Name | Last commit |
|------|-------------|
| `core/` | feat(enums): DocumentStatus, FieldValueType, OcrProvider, UserRole |
| `db/` | Sprint 2 : API Labellisation complète |
| `enums/` | Sprint 2 : API Labellisation complète |
| `migrations/` | Sprint 2 : API Labellisation complète |
| `models/` | feat(orm): format models files |
| `schemas/` | feat(adam_core): add schemas, utils and static assets |
| `static/` | feat(adam_core): add schemas, utils and static assets |
| `utils/` | Sprint 2 : API Labellisation complète |
| `README.md` | Sprint 2 : API Labellisation complète |
| `__init__.py` | chore(repo): init structure adam_core / adam_api / pyproject |
| `alembic.ini` | Sprint 2 : API Labellisation complète |

---

### Page 06 — `src/adam_core/README.md` (lines ~1–40)

```markdown
# adam_core

Package transverse du projet ADAM. Il contient tous les composants partagés entre les différents services : modèles ORM, configuration, migrations, énumérations et utilitaires.

`adam_core` ne dépend d'aucun autre package ADAM. C'est lui qui est importé par `adam_api`, et potentiellement par tout futur service (`adam_worker`, `adam_cli`, etc.).

## Structure

```text
adam_core/
├── core/
│   └── config.py           Configuration .env transverse (CoreSettings)
├── db/
│   ├── base.py             DeclarativeBase SQLAlchemy partagée
│   └── session.py          Engine async
├── enums/
│   ├── ocr.py              OcrProvider, StorageMode
│   ├── roles.py            UserRole, ExportFormat
│   └── status.py           DocumentStatus, FieldValueType...
├── migrations/
│   ├── env.py              Configuration Alembic async
│   ├── script.py.mako      Template de migration
│   └── versions/           Fichiers de migration générés
└── models/
    ├── __init__.py         Import de tous les modèles (requis pour Alembic)
    ├── organisation.py
    └── user.py
```
```

---

### Page 07 — `src/adam_core/README.md` (continued)

```markdown
models/
├── __init__.py         Import de tous les modèles (requis pour Alembic)
├── organisation.py
├── user.py
└── user_project.py
...
schemas/                Schémas Pydantic partagés
utils/
└── volumetry.py        Estimation de volumétrie BDD
...

## Configuration

`adam_core` expose `CoreSettings`, une classe `pydantic-settings` qui lit les variables d'environnement depuis un fichier `.env`.

```python
from adam_core.core.config import get_core_settings

settings = get_core_settings()
print(settings.async_database_url)
```

Les variables lues par `CoreSettings` :

| Variable | Défaut | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `'dev'` | Environnement : dev, staging, prod |
| `APP_NAME` | `'ADAM'` | Nom de l'application |
| `APP_VERSION` | `'0.1.0'` | Version |
| `POSTGRES_USER` | `'postgres'` | Utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | `''` | Mot de passe PostgreSQL |
| `POSTGRES_HOST` | `'localhost'` | Hôte PostgreSQL |
| `POSTGRES_PORT` | `'5432'` | Port PostgreSQL |
```

---

### Page 08 — `src/adam_core/README.md` (continued)

```markdown
| `POSTGRES_HOST` | 'localhost' | Hôte PostgreSQL |
| `POSTGRES_PORT` | '5432' | Port PostgreSQL |
| `POSTGRES_DB`   | 'adam_db'   | Nom de la base |
| `LOG_LEVEL`     | 'DEBUG'     | Niveau de log |
| `LOG_FORMAT`    | 'text'      | Format de log : text ou json |

Comme exemple, `adam_api` hérite de `CoreSettings` et y ajoute ses propres variables (CORS, JWT, OCR...).

---

## Migrations Alembic

Les migrations sont gérées par Alembic avec SQLAlchemy en mode async.

### Workflow standard

**1. Modifier un modèle ORM**

Éditer le fichier correspondant dans `models/`. Par exemple ajouter une colonne sur `Document`.

**2. Générer la migration**

```powershell
# dans la racine du projet
python -m alembic -c src/adam_core/alembic.ini revision --autogenerate -m "description du changement"
```

Alembic compare l'état des modèles Python avec l'état réel de la base et génère automatiquement le script de migration dans `migrations/versions/`.

**3. Vérifier le fichier généré**

Toujours ouvrir et lire le fichier généré avant de l'appliquer. Alembic peut manquer certains cas (renommage de colonne, contraintes complexes).
```

---

### Page 09 — `src/adam_core/README.md` (continued)

```markdown
**4. Appliquer la migration**

```bash
python -m alembic -c src/adam_core/alembic.ini upgrade head
```

### Commandes utiles

```bash
# Etat actuel de la base
python -m alembic -c src/adam_core/alembic.ini current

# Historique des migrations
python -m alembic -c src/adam_core/alembic.ini history --verbose

# Revenir à la migration précédente
python -m alembic -c src/adam_core/alembic.ini downgrade -1

# Revenir à l'état initial (vide)
python -m alembic -c src/adam_core/alembic.ini downgrade base

# Appliquer toutes les migrations en attente
python -m alembic -c src/adam_core/alembic.ini upgrade head
```

### Règles importantes

* Ne jamais modifier un fichier de migration déjà appliqué en production.
* Toujours vérifier le fichier généré avant `upgrade head`.
* En DEV, si le schéma est cassé : `downgrade base` puis `upgrade head`.
* Le fichier `migrations/versions/__init__.py` ne doit pas exister (Alembic gère ce dossier seul).
```

---

### Page 10 — `src/adam_core/README.md` (continued)

```markdown
## Modèles ORM

Les modèles suivent les conventions SQLAlchemy 2.x avec `Mapped` et `mapped_column`.

### Conventions de nommage en base

| Type | Format | Exemple |
| :--- | :--- | :--- |
| Table | `snake_case singulier` | `document_field` |
| Index | `ix_<table_>_<colonne>` | `ix_user_email` |
| Unique | `uq_<table_>_<colonnes>` | `uq_field_spec_schema_group_key` |
| FK | `fk_<table_>_<colonne>_<table_cible>` | `fk_user_organisation_id_organisation` |
| PK | `pk_<table_>` | `pk_document` |
| Check | `ck_<table_>_<nom>` | `ck_field_spec_polygon_length` |

### Relations et lazy loading

Toutes les relations sont déclarées avec `lazy="noload"`. Elles ne sont jamais chargées automatiquement, il faut les demander explicitement via `selectinload` ou `db.refresh`.

```python
from sqlalchemy.orm import selectinload
```
```

---

### Page 11 — `src/adam_core/README.md` (continued)

```markdown
## Relations et lazy loading

Toutes les relations sont déclarées avec `lazy="noload"`. Elles ne sont jamais chargées automatiquement, il faut les demander explicitement via `selectinload` ou `db.refresh`.

```python
from sqlalchemy.orm import selectinload

# Charger un dataset avec ses documents
result = await db.execute(
    select(Dataset)
    .where(Dataset.id == 1)
    .options(selectinload(Dataset.documents))
)
dataset = result.scalar_one()
```

## Utilitaires

### Volumétrie

```python
from adam_core.utils.volumetry import estimate_row_size, estimate_table_size, format_size

# Taille estimée d'une ligne
size = estimate_row_size(document)
print(format_size(size)) # ~ 1.2 kB

# Taille estimée d'une table entière
stats = estimate_table_size(documents)
print(stats["total_human"]) # ~ "45.3 MB"
print(stats["avg_human"]) # ~ "512.0 B"
```
```

---

### Page 12 — `src/adam_core/README.md` (continued)

```markdown
dataset = result.scalar_one()

# Utilitaires

## Volumétrie

```python
from adam_core.utils.volumetry import estimate_row_size, estimate_table_size, format_size

# Taille estimée d'une ligne
size = estimate_row_size(document)
print(format_size(size)) # "1.2 KB"

# Taille estimée d'une table entière
stats = estimate_table_size(documents)
print(stats["total_human"]) # "45.3 MB"
print(stats["avg_human"]) # "512.0 B"
```

Il s'agit d'une estimation basée sur les types PostgreSQL. Pour la taille réelle en base :

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```
```

---

### Page 13 — Directory listing: `src/`

| Name | Last commit |
|------|-------------|
| `adam_api` | Sprint 2 : API Labellisation complète |
| `adam_core` | Sprint 2 : API Labellisation complète |
| `adam_worker/src` | Sprint 2 : API Labellisation complète |

---

### Page 14 — Directory listing: `src/adam_worker/src/`

| Name | Last commit |
|------|-------------|
| `consensus_worker.py` | Sprint 2 : API Labellisation complète |

---

### Page 15 — `src/adam_worker/src/consensus_worker.py` (lines 1–35)

```python
"""
Consensus Worker retry des documents en attente de résolution.

Tourne périodiquement et relance try_resolve sur les documents
qui ont atteint required_operators jobs submitted mais ne sont
pas encore VALIDATED (echec background task ou conflit non résolu).

Sprint 2 : Logique de polling implementée, a refiner dans la Sprint 3
"""

from __future__ import annotations

from sqlalchemy import select

from adam_api.services.consensus import try_resolve
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

async def run_pending_consensus() -> None:
    """
    Cherche tous les documents PENDING_CONSENSUS et tente de résoudre
    leur consensus.

    Idempotent : try_resolve gère les gardes internes (count, already validated).
    """
    async with get_async_session() as db:
        pending = (
            await db.execute(
                select(Document.id, Document.dataset_id).where(
                    Document.status == DocumentStatus.PENDING_CONSENSUS.value
```

---

### Page 16 — `src/adam_worker/src/consensus_worker.py` (lines 21–54)

```python
logger = get_logger(__name__)

async def run_pending_consensus() -> None:
    """
    Cherche tous les documents PENDING_CONSENSUS et tente de résoudre
    leur consensus.

    Idempotent : try_resolve gère les gardes internes (count, already validated).
    """
    async with get_async_session() as db:
        pending = (
            await db.execute(
                select(Document.id, Document.dataset_id).where(
                    Document.status == DocumentStatus.PENDING_CONSENSUS.value
                )
            )
        ).all()

        if not pending:
            logger.debug("consensus_worker: aucun document en attente")
            return

        logger.info("consensus_worker: %s document(s) a traiter", len(pending))

        for doc_id, dataset_id in pending:
            try:
                await try_resolve(doc_id, dataset_id)
            except Exception:
                logger.exception("consensus_worker: echec [document_id=%s]", doc_id)

    # TODO Sprint 3 : brancher avec le scheduler (à définir)
```

---

### Page 17 — Directory listing: `src/adam_core/core/`

| Name | Last commit |
|------|-------------|
| `config.py` | feat(enums): DocumentStatus, FieldValueType, OcrProvider, UserRole |

---

### Page 18 — `src/adam_core/core/config.py` (lines 1–35)

```python
"""
Settings transverses partagees par tous les packages ADAM.
Heriter de CoreSettings pour ajouter des settings specifiques.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str
    app_name: str
    app_version: str

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str

    # Logging
    log_level: str = Field(default="DEBUG")
    log_format: str = Field(default="text")
```

---

### Page 19 — `src/adam_core/core/config.py` (lines 30–62)

```python
    postgres_host: str
    postgres_port: int
    postgres_db: str

    # Logging
    log_level: str = Field(default="DEBUG")
    log_format: str = Field(default="text")

    # Computed
    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == 'dev'

    @property
    def async_database_url(self) -> str:
        return str(
            URL.create(
                drivername="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                database=self.postgres_db,
            )
        )

@lru_cache
def get_core_settings() -> CoreSettings:
    return CoreSettings()  # type: ignore[call-arg]

core_settings = get_core_settings()
```

---

### Page 20 — Directory listing: `src/adam_core/db/`

| Name | Last commit |
|------|-------------|
| `__init__.py` | chore(repo): init structure adam_core / adam_api / pyproject |
| `base.py` | feat(config): CoreSettings pydantic-settings, async engine, URL create |
| `session.py` | Sprint 2 : API Labellisation complète |

---

### Page 21 — `src/adam_core/db/__init__.py`

**Empty file** (0 B)

---

### Page 22 — `src/adam_core/db/base.py` (lines 1–29)

```python
"""
DeclarativeBase partagée par tous les modèles ORM du projet.

Convention de nommage PostgreSQL :
  - tables  : snake_case, singulier (ex : organisation, user_project)
  - index   : ix_%(column_0_label)s
  - unique  : uq_%(table_name)s_%(column_0_name)s
  - fk      : fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s
  - pk      : pk_%(table_name)s
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Naming conventions PostgreSQL
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    """Base déclarative unique pour tous les modèles ORM."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

---

### Page 23 — `src/adam_core/db/session.py` (lines 1–35)

```python
"""Engine SQLAlchemy async et session factory pour ADAM."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

_engine = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

def init_engine(database_url: str, *, echo: bool = False) -> None:
    global _engine, _async_session_factory
    logger.info("DB -> %s", database_url.split("@")[-1])
    _engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    _async_session_factory = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False
    )

def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Appelez init_engine() d'abord.")
    return _engine
```

---

### Page 24 — `src/adam_core/db/session.py` (lines 22–55)

```python
def init_engine(database_url: str, *, echo: bool = False) -> None:
    global _engine, _async_session_factory
    logger.info("DB -> %s", database_url.split("@")[-1])
    _engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    _async_session_factory = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False
    )

def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Appelez init_engine() d'abord.")
    return _engine

async def create_tables() -> None:
    from adam_core.db.base import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    if _async_session_factory is None:
        raise RuntimeError("Session factory non initialisée.")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

### Page 25 — Directory listing: `src/adam_core/enums/`

| Name | Last commit |
|------|-------------|
| `__init__.py` | chore(repo): init structure adam_core / adam_api / pyproject |
| `ocr.py` | feat(enums): DocumentStatus, FieldValueType, OcrProvider, UserRole |
| `roles.py` | feat(enums): DocumentStatus, FieldValueType, OcrProvider, UserRole |
| `status.py` | Sprint 2 : API Labellisation complète |

---

### Page 26 — `src/adam_core/enums/__init__.py`

**Empty file** (0 B)

---

### Page 27 — `src/adam_core/enums/ocr.py` (lines 1–26)

```python
"""
Énumérations liées aux moteurs OCR et au mode de stockage
des résultats OCR.
"""

from enum import Enum

class OcrProvider(str, Enum):  # pylint: disable=invalid-name
    """Fournisseurs OCR supportés pour la pré-alimentation des datasets."""

    PULSAR = "PULSAR"  # pylint: disable=invalid-name
    MISTRAL = "MISTRAL"  # pylint: disable=invalid-name

class StorageMode(str, Enum):  # pylint: disable=invalid-name
    """
    Mode de stockage du résultat JSON brut OCR dans OCR_RESULT.

    - JSONB : le JSON est stocké directement en base
    - FILE : le JSON est stocké sur PV
    """

    JSONB = "JSONB"  # pylint: disable=invalid-name
    FILE = "FILE"  # pylint: disable=invalid-name
```

---

## Merged complete files (deduplicated from overlapping pages)

### `src/adam_api/services/consensus.py` (partial — lines 36–155 only)

```python
        Déclenchement : background task depuis submit_job.
        """
        try:
            async with get_async_session() as db:
                return await _resolve(document_id, dataset_id, db)
        except Exception:
            logger.exception(
                "try_resolve echoue [document_id=%s dataset_id=%s]",
                document_id,
                dataset_id,
            )
            return {"error": "try_resolve echoue", "document_id": document_id}

def _apply_vote(df: DocumentField, field_proposals: list[FieldProposal]) -> bool:
    """Applique le vote majoritaire. Retourne True si consensus, False si dispute."""
    if not field_proposals:
        df.consensus_reached = True
        df.resolved_value = df.ocr_value
        df.status = DocumentFieldStatus.VALIDATED.value
        return True

    values = [p.value for p in field_proposals]
    top_value, top_count = Counter(values).most_common(1)[0]

    if top_count > len(values) / 2:
        df.consensus_reached = True
        df.resolved_value = top_value
        df.status = DocumentFieldStatus.VALIDATED.value
        return True

    df.consensus_reached = False
    df.status = DocumentFieldStatus.DISPUTED.value
    return False

async def _resolve(document_id: int, dataset_id: int, db: AsyncSession) -> dict[str, Any]:
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
        logger.error("try_resolve: dataset introuvable [dataset_id=%s]", dataset_id)
        return {"document_id": document_id, "status": "error", "reason": "dataset introuvable"}

    document = await db.get(Document, document_id)
    if not document:
        logger.error("try_resolve: document introuvable [document_id=%s]", document_id)
        return {"document_id": document_id, "status": "error", "reason": "document introuvable"}

    if document.status == DocumentStatus.VALIDATED.value:
        logger.debug("try_resolve: document déjà validé [document_id=%s]", document_id)
        return {"document_id": document_id, "status": "already_validated"}

    submitted_count: int = (
        await db.execute(
            select(count(Job.id))
            .where(Job.document_id == document_id)
            .where(Job.state == JobState.SUBMITTED.value)
        )
    ).scalar_one()

    if submitted_count < dataset.required_operators:
        logger.debug(
            "try_resolve: attente [document_id=%s jobs=%s/%s]",
            document_id,
            submitted_count,
            dataset.required_operators,
        )
        return {
            "document_id": document_id,
            "status": "waiting",
            "submitted_jobs": submitted_count,
            "required_operators": dataset.required_operators,
        }

    fields = (
        await db.execute(select(DocumentField).where(DocumentField.document_id == document_id))
        .scalars()
        .all()
    )

    proposals = (
        (
            await db.execute(
                select(FieldProposal)
                .join(Job, FieldProposal.job_id == Job.id)
                .where(Job.document_id == document_id)
                .where(Job.state == JobState.SUBMITTED.value)
            )
        )
        .scalars()
        .all()
    )

    by_field: dict[int, list[FieldProposal]] = {}
    for p in proposals:
        by_field.setdefault(p.document_field_id, []).append(p)

    all_resolved = all(_apply_vote(df, by_field.get(df.id, [])) for df in fields)

    if all_resolved:
        document.status = DocumentStatus.VALIDATED.value
        logger.info("document valide [document_id=%s]", document_id)
    else:
        disputed = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
        logger.info(
            "consensus partiel [document_id=%s disputed=%s/%s]",
            document_id,
            disputed,
            len(fields),
        )

    disputed_count = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
    return {
        "document_id": document_id,
        "document_status": document.status,
        "fields_total": len(fields),
        "fields_resolved": len(fields) - disputed_count,
        "fields_disputed": disputed_count,
        "submitted_jobs": submitted_count,
    }
```

**Inferred imports (not visible in Pds5):** `Counter`, `count`, `select`, `AsyncSession`, `Any`, models (`Dataset`, `Document`, `DocumentField`, `FieldProposal`, `Job`), enums (`DocumentStatus`, `DocumentFieldStatus`, `JobState`), `get_async_session`, `logger`, and `async def try_resolve(...)` signature at lines 1–35.

---

## Coverage gaps (not in Pds5)

These files are **referenced but not shown** in this PDF:

- `consensus.py` lines 1–35 (imports + `try_resolve` header)
- `src/adam_core/enums/roles.py`, `status.py`
- All `models/`, `schemas/`, `utils/`, `migrations/`, `adam_api/` (except `consensus.py` tail)
- `alembic.ini`, `pyproject.toml`, root project files

Other PDF sets in the screenshots folder may contain these.

[REDACTED]