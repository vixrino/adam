I'll list the Pds2 screenshots, convert any missing pages from the PDF, then transcribe code from each image.

[REDACTED]
Only 3 of 51 pages exist — converting the full PDF now.

[REDACTED]
[REDACTED]
[REDACTED]
All 51 pages are ready. Reading screenshots in batches to transcribe the code.

[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
Compiling the full structured report for all 51 pages.

[REDACTED]
# Pds2 Screenshot Transcription Report — adam

**Source:** lot PDF transcrit *(fichiers supprimés — anonymisation)*  
**Converted:** 51 PNGs at `Pds2-01.png` … `Pds2-51.png` (120 DPI)

---

## Page 01 — `src/adam_core/models/ocr_result.py` (lines 1–35)

```python
"""
Table OCR_RESULT : réponse JSON brute du moteur OCR.

On suit résultat OCR par document par dataset.
Contrainte unique sur (document_id, dataset_id).
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.ocr import StorageMode

class OcrResult(Base):
    __tablename__ = "ocr_result"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "dataset_id",
            name="uq_ocr_result_document_dataset",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
```

---

## Page 02 — `src/adam_core/models/ocr_result.py` (lines 35–71)

```python
        index=True,
    )
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=StorageMode.JSONB.value,
        comment="JSONB = stocké en base, File = stocké sur PSC",
    )
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Réponse OCR complète. Null si storage_mode=file",
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="ocr_results",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<OcrResult id={self.id} document_id={self.document_id} "
            f"mode={self.storage_mode}>"
        )
```

---

## Page 03 — `src/adam_core/models/organisation.py` (lines 1–35)

```python
"""
Table ORGANISATION : tenant de la plateforme ADAM.

Chaque user appartient directement à une organisation via
User.organisation_id. Pas de table de jointure USER_ORGANISATION.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base

class Organisation(Base):
    __tablename__ = "organisation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

---

## Page 04 — `src/adam_core/models/organisation.py` (lines 17–50)

```python
class Organisation(Base):
    __tablename__ = "organisation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    users: Mapped[list["User"]] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="organisation",
        lazy="raise",
    )
    projects: Mapped[list["Project"]] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="organisation",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<Organisation id={self.id} name={self.name} slug={self.slug}>"
```

---

## Page 05 — `src/adam_core/models/project.py` (lines 1–37)

```python
"""
Table PROJECT : unité de travail rattachée à une organisation.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import ProjectStatus

class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ProjectStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
```

---

## Page 06 — `src/adam_core/models/project.py` (lines 36–74)

```python
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    organisation: Mapped["Organisation"] = relationship(  # type: ignore[name-defined]
        "Organisation",
        back_populates="projects",
        lazy="noload",
    )
    # Tous les schémas créés dans ce projet
    schemas: Mapped[list["DocSchema"]] = relationship(  # type: ignore[name-defined]
        "DocSchema",
        foreign_keys="DocSchema.project_id",
        back_populates="project",
        lazy="noload",
    )
    datasets: Mapped[list["Dataset"]] = relationship(  # type: ignore[name-defined]
        "Dataset",
        back_populates="project",
        lazy="noload",
    )
    user_projects: Mapped[list["UserProject"]] = relationship(  # type: ignore[name-defined]
        "UserProject",
        back_populates="project",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        schemas_count = len(self.schemas) if self.schemas else "?"
        datasets_count = len(self.datasets) if self.datasets else "?"
        users_count = len(self.user_projects) if self.user_projects else "?"
        return (
            f"<Project id={self.id} name={self.name}>"
```

---

## Page 07 — `src/adam_core/models/project.py` (lines 45–78)

```python
    # organisation: Mapped["Organisation"] = relationship(  # type: ignore[name-defined]
    #     "Organisation",
    #     back_populates="projects",
    #     lazy="noload",
    # )
    # Tous les schémas créés dans ce projet
    schemas: Mapped[list["DocSchema"]] = relationship(  # type: ignore[name-defined]
        "DocSchema",
        foreign_keys="DocSchema.project_id",
        back_populates="project",
        lazy="noload",
    )
    datasets: Mapped[list["Dataset"]] = relationship(  # type: ignore[name-defined]
        "Dataset",
        back_populates="project",
        lazy="noload",
    )
    user_projects: Mapped[list["UserProject"]] = relationship(  # type: ignore[name-defined]
        "UserProject",
        back_populates="project",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        schemas_count = len(self.schemas) if self.schemas else "?"
        datasets_count = len(self.datasets) if self.datasets else "?"
        users_count = len(self.user_projects) if self.user_projects else "?"
        return (
            f"<Project id={self.id} name={self.name}>"
            f"status={self.status} org_id={self.organisation_id}>"
            f"schemas={schemas_count} datasets={datasets_count} users={users_count}>"
        )
```

---

## Page 08 — `src/adam_core/models/user.py` (lines 1–37)

```python
"""
Table USER : utilisateur de la plateforme ADAM.

L'accès aux projets et les rôles associés sont gérés via USER_PROJECT.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import UserStatus

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    matricule: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
```

---

## Page 09 — `src/adam_core/models/user.py` (lines 35–73)

```python
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=UserStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organisation: Mapped["Organisation"] = relationship(  # type: ignore[name-defined]
        "Organisation",
        back_populates="users",
        lazy="noload",
    )
    user_projects: Mapped[list["UserProject"]] = relationship(  # type: ignore[name-defined]
        "UserProject",
        back_populates="user",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]
        "Job",
        back_populates="agent",
        foreign_keys="Job.agent_id",
        lazy="noload",
    )
```

---

## Page 10 — `src/adam_core/models/user.py` (lines 46–78)

```python
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organisation: Mapped["Organisation"] = relationship(  # type: ignore[name-defined]
        "Organisation",
        back_populates="users",
        lazy="selectin",
    )
    user_projects: Mapped[list["UserProject"]] = relationship(  # type: ignore[name-defined]
        "UserProject",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]
        "Job",
        back_populates="agent",
        foreign_keys="Job.agent_id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} status={self.status!r}>"
```

---

## Page 11 — `src/adam_core/models/user_project.py` (lines 1–32)

```python
"""
Table USER_PROJECT : jointure User / Project avec rôle.

Le rôle détermine les actions autorisées au sein du projet :
- operator : labellise les documents
- supervisor : supervise et valide
- admin : gestion complète
Clé primaire composite sur (user_id, project_id).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.roles import UserRole

class UserProject(Base):
    __tablename__ = "user_project"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="CASCADE"),
        primary_key=True,
    )
```

---

## Page 12 — `src/adam_core/models/user_project.py` (lines 31–67)

```python
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=UserRole.OPERATOR.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="user_projects",
        lazy="noload",
    )
    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="user_projects",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<UserProject user_id={self.user_id} "
            f"project_id={self.project_id} role={self.role!r}>"
        )
```

---

## Page 13 — `src/adam_core/static/` (directory listing)

**No code.** Contents:
- `favicon.ico`

---

## Page 14 — `src/adam_core/utils/` (directory listing)

**No code.** Contents:
| File | Last commit |
|---|---|
| `__init__.py` | chore(repo): init structure adam_core / adam_api / pyproject |
| `exceptions.py` | Sprint 2 : API Labellisation complète |
| `logging.py` | Sprint 2 : API Labellisation complète |
| `volumetry.py` | feat(adam_core): add schemas, utils and static assets |

---

## Page 15 — `src/adam_core/utils/__init__.py`

**Empty file** (0 B).

---

## Page 16 — `src/adam_core/utils/exceptions.py` (lines 1–34)

```python
"""
Exceptions HTTP standardisées et handler unifié pour FastAPI.
"""

import logging
from typing import Any, NoReturn, Optional, Type, cast

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

# Handler middleware

async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler unifié logue toutes les erreurs HTTP avec contexte.
    4xx -> WARNING, 5xx -> ERROR
    """
    http_exc = cast(HTTPException, exc)
    level = logging.WARNING if http_exc.status_code < 500 else logging.ERROR

    logger.log(
        level,
        "HTTP %s - %s %s - %s",
        http_exc.status_code,
        request.method,
        request.url.path,
        http_exc.detail,
    )
```

---

## Page 17 — `src/adam_core/utils/exceptions.py` (lines 32–69)

```python
        request.method,
        request.url.path,
        http_exc.detail,
    )

    return JSONResponse(
        status_code=http_exc.status_code,
        content={"detail": http_exc.detail},
    )

# Messages templates

NOT_FOUND = "{} introuvable"
ALREADY_ARCHIVED = "{} déjà archivé"
NOT_ARCHIVED = "{} non archivé"
ALREADY_EXISTS = "{} déjà existant"
CONFLICT = "{} : {}"

# Helpers

def _name(model: Type[Any]) -> str:
    name = getattr(model, "__tablename__", model.__name__)
    return name.capitalize()

def raise_not_found(model: Type[Any], detail: Optional[str] = None) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=detail if detail else NOT_FOUND.format(_name(model)),
    )

def raise_already_archived(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=ALREADY_ARCHIVED.format(_name(model)))

def raise_not_archived(model: Type[Any]) -> NoReturn:
```

---

## Page 18 — `src/adam_core/utils/exceptions.py` (lines 51–84)

```python
# Helpers

def _name(model: Type[Any]) -> str:
    name = getattr(model, "__tablename__", model.__name__)
    return name.capitalize()

def raise_not_found(model: Type[Any], detail: Optional[str] = None) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=detail if detail else NOT_FOUND.format(_name(model)),
    )

def raise_already_archived(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=ALREADY_ARCHIVED.format(_name(model)))

def raise_not_archived(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=NOT_ARCHIVED.format(_name(model)))

def raise_already_exists(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=ALREADY_EXISTS.format(_name(model)))

def raise_conflict(model: Type[Any], detail: str) -> NoReturn:
    raise HTTPException(status_code=409, detail=CONFLICT.format(_name(model), detail))

def raise_unprocessable(detail: str) -> NoReturn:
    raise HTTPException(status_code=422, detail=detail)
```

---

## Page 19 — `src/adam_core/utils/logging.py` (lines 1–30)

```python
from __future__ import annotations

import logging
from logging import config as logging_config
from typing import Any

from adam_core.core.config import CoreSettings

_FORMATTERS_JSON = {"json": {"class": "exa.logger.formatter.JsonFormatter"}}

_FORMATTERS_TEXT = {
    "text": {
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }
}

def build_log_config(settings: CoreSettings) -> dict[str, Any]:
    """Construit le dictConfig logging dans l'application."""
    use_json = settings.log_format.lower() == "json"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "root": {
            "handlers": ["console"],
            "level": settings.log_level.upper(),
        },
        "handlers": {
            "console": {
```

---

## Page 20 — `src/adam_core/utils/logging.py` (lines 17–52)

```python
def build_log_config(settings: CoreSettings) -> dict[str, Any]:
    """Construit le dictConfig logging sans l'appliquer."""
    use_json = settings.log_format.lower() == "json"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "root": {
            "handlers": ["console"],
            "level": settings.log_level.upper(),
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if use_json else "text",
            }
        },
        "formatters": _FORMATTERS_JSON if use_json else _FORMATTERS_TEXT,
    }

def setup_logging(settings: CoreSettings) -> None:
    """Applique le dictConfig logging."""
    logging.config.dictConfig(build_log_config(settings))

def get_logger(name: str) -> logging.Logger:
    """Retourne un logger standard pour le module appelant.

    Usage :
        logger = get_logger(__name__)
        logger.info("message")
    """
    return logging.getLogger(name)
```

---

## Page 21 — `src/adam_core/utils/volumetry.py` (lines 1–35)

```python
"""
Estimation de la taille mémoire d'une ligne ORM en octets.

Méthode : sérialise chaque colonne en sa représentation stockée
(string JSON, bytes, int...) et additionne les tailles.

Usage :
    from adam_core.utils.volumetry import estimate_row_size, format_size

    size_bytes = estimate_row_size(dataset)
    print(format_size(size_bytes))  # "1.2 KB"
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, Sequence

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase

def estimate_row_size(instance: DeclarativeBase) -> int:
    """
    Estime la taille en octets d'une ligne ORM.

    Ne compte que les colonnes scalaires (pas les relationnels).
    Chaque valeur est estimée selon son type de stockage PostgreSQL.

    Returns:
        Taille estimée en octets.
    """
    total = 0
    mapper = inspect(type(instance))
```

---

## Page 22 — `src/adam_core/utils/volumetry.py` (lines 35–73)

```python
    for column in mapper.columns:
        value = getattr(instance, column.key, None)
        total += _estimate_value(value)

    return total

def estimate_table_size(instances: Sequence[Any]) -> Dict[str, Any]:
    """
    Estime la taille totale d'une liste de lignes ORM.

    Returns:
        Dict avec total_bytes, row_count, avg_bytes_per_row.
    """
    if not instances:
        return {"total_bytes": 0, "row_count": 0, "avg_bytes_per_row": 0}

    sizes = [estimate_row_size(r) for r in instances]
    total = sum(sizes)
    return {
        "total_bytes": total,
        "total_human": format_size(total),
        "row_count": len(instances),
        "avg_bytes_per_row": total // len(instances),
        "avg_human": format_size(total // len(instances)),
        "min_bytes": min(sizes),
        "max_bytes": max(sizes),
    }

def format_size(size_bytes: int) -> str:
    """Convertit des octets en string lisible."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"
```

---

## Page 23 — `src/adam_core/utils/volumetry.py` (lines 71–104)

```python
    return f"{size_bytes:.1f} TB"

def _estimate_value(value: Any) -> int:  # pylint: disable=too-many-return-statements
    """Estime la taille d'une valeur selon son type Python."""

    if value is None:
        return 1  # NULL = 1 octet au PostgreSQL

    if isinstance(value, bool):
        return 1  # BOOLEAN = 1 octet

    if isinstance(value, int):
        return 4  # INTEGER = 4 octets

    if isinstance(value, float):
        return 8  # FLOAT8 = 8 octets

    if isinstance(value, str):
        return len(value.encode("utf-8"))  # VARCHAR = taille réelle UTF-8

    if isinstance(value, datetime):
        return 8  # TIMESTAMPTZ = 8 octets

    if isinstance(value, (dict, list)):
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))  # JSONB

    if isinstance(value, bytes):
        return len(value)  # BYTEA

    # Fallback
    return sys.getsizeof(value)
```

---

## Page 24 — `src/adam_core/README.md` (rendered, no line numbers)

```markdown
# adam_core

Package transverse du projet ADAM. Il contient tous les composants partagés entre les différents services : modèles ORM, configuration, migrations, énumérations et utilitaires.

`adam_core` ne dépend d'aucun autre package ADAM. C'est lui qui est importé par `adam_api`, et potentiellement par tout futur service (`adam_worker`, `adam_cli`, etc.).

## Structure

adam_core/
├── core/
│   └── config.py          Configuration .env transverse (CoreSettings)
├── db/
│   ├── base.py            DeclarativeBase SQLAlchemy partagée
│   └── session.py         Engine async
├── enums/
│   ├── ocr.py             OcrProvider, StorageMode
│   ├── roles.py           UserRole, ExportFormat
│   └── status.py          DocumentStatus, FieldValueType...
└── migrations/
    └── env.py             Configuration Alembic async
```

---

## Page 25 — `src/adam_core/README.md` (continued)

```markdown
├── ocr.py              OcrProvider, StorageMode
├── roles.py            UserRole, ExportFormat
├── status.py           DocumentStatus, FieldValueType...
├── migrations/
│   ├── env.py          Configuration Alembic async
│   ├── script.py.mako  Template de migration
│   └── versions/       Fichiers de migration générés
├── models/
│   ├── __init__.py     Import de tous les modèles (requis pour Alembic)
│   ├── organisation.py
│   ├── user.py
│   └── user_project.py
│   └── ...
├── schemas/            Schémas Pydantic partagés
└── utils/
    ├── volumetry.py    Estimation de volumétrie BDD
    └── ...

## Configuration

`adam_core` expose `CoreSettings`, une classe `pydantic-settings` qui lit les variables d'environnement depuis un fichier `.env`.

from adam_core.core.config import get_core_settings

settings = get_core_settings()
print(settings.async_database_url)

Les variables lues par `CoreSettings` :
```

---

## Page 26 — `src/adam_core/README.md` (continued)

| Variable | Défaut | Description |
|---|---|---|
| `APP_ENV` | `dev` | Environnement : dev, staging, prod |
| `APP_NAME` | `ADAM` | Nom de l'application |
| `APP_VERSION` | `0.1.0` | Version |
| `POSTGRES_USER` | `postgres` | Utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | `` | Mot de passe PostgreSQL |
| `POSTGRES_HOST` | `localhost` | Hôte PostgreSQL |
| `POSTGRES_PORT` | `5432` | Port PostgreSQL |
| `POSTGRES_DB` | `adam_db` | Nom de la base |
| `LOG_LEVEL` | `DEBUG` | Niveau de log |
| `LOG_FORMAT` | `text` | Format de log : text ou json |

Comme exemple, `adam_api` hérite de `CoreSettings` et y ajoute ses propres variables (CORS, JWT, OCR...).

---

## Migrations Alembic

Les migrations sont gérées par Alembic avec SQLAlchemy en mode async.

### Workflow standard

**1. Modifier un modèle ORM**

Éditer le fichier correspondant dans `models/`. Par exemple ajouter une colonne sur `Document`.

**2. Générer la migration**

---

## Page 27 — `src/adam_core/README.md` (continued)

```powershell
# dans la racine du projet
python -m alembic -c src/adam_core/alembic.ini revision --autogenerate -m "description du changement"
```

Alembic compare l'état des modèles Python avec l'état réel de la base et génère automatiquement le script de migration dans `migrations/versions/`.

**3. Vérifier le fichier généré**

Toujours ouvrir et lire le fichier généré avant de l'appliquer. Alembic peut manquer certains cas (renommage de colonne, contraintes complexes).

**4. Appliquer la migration**

```
python -m alembic -c src/adam_core/alembic.ini upgrade head
```

**Commandes utiles**

```
# État actuel de la base
python -m alembic -c src/adam_core/alembic.ini current

# Historique des migrations
python -m alembic -c src/adam_core/alembic.ini history --verbose
```

---

## Page 28 — `src/adam_core/README.md` (continued)

```bash
# Historique des migrations
python -m alembic -c src/adam_core/alembic.ini history --verbose

# Revenir à la migration précédente
python -m alembic -c src/adam_core/alembic.ini downgrade -1

# Revenir à l'état initial (vide)
python -m alembic -c src/adam_core/alembic.ini downgrade base

# Appliquer toutes les migrations en attente
python -m alembic -c src/adam_core/alembic.ini upgrade head
```

#### Règles importantes
- Ne jamais modifier un fichier de migration déjà appliqué en production.
- Toujours vérifier le fichier généré avant `upgrade head`.
- En DEV, si le schéma est cassé : `downgrade base` puis `upgrade head`.
- Le fichier `migrations/versions/__init__.py` ne doit pas exister (Alembic gère ce dossier seul).

#### Modèles ORM
Les modèles suivent les conventions SQLAlchemy 2.x avec `Mapped` et `mapped_column`.

#### Conventions de nommage en base
| Type | Format | Exemple |
|---|---|---|
| Table | `snake_case singulier` | `document_field` |
| Index | `ix_<table_name>_<column_name>` | `ix_user_email` |
| Unique | `uq_<table_name>_<column_names>` | `uq_field_spec_schema_group_key` |

---

## Page 29 — `src/adam_core/README.md` (continued)

| Type | Pattern | Exemple |
|---|---|---|
| Unique | `uq_<table>_<colonnes>` | `uq_field_spec_schema_group_key` |
| FK | `fk_<table>_<colonne>_<table_cible>` | `fk_user_organisation_id_organisation` |
| PK | `pk_<table>` | `pk_document` |
| Check | `ck_<table>_<nom>` | `ck_field_spec_polygon_length` |

#### Relations et lazy loading
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

#### Utilitaires

##### Volumétrie

```python
from adam_core.utils.volumetry import estimate_row_size, estimate_table_size, format_size

# Taille estimée d'une ligne
size = estimate_row_size(document)
```

---

## Page 30 — `src/adam_core/README.md` (continued)

```python
from adam_core.utils.volumetry import estimate_row_size, estimate_table_size, format_size

# Taille estimée d'une ligne
size = estimate_row_size(document)
print(format_size(size))  # "1.2 KB"

# Taille estimée d'une table entière
stats = estimate_table_size(documents)
print(stats["total_human"])    # "45.3 MB"
print(stats["avg_human"])      # "512.0 B"
```

Il s'agit d'une estimation basée sur les types PostgreSQL. Pour la taille réelle en base :

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

---

## Page 31 — `src/adam_core/__init__.py`

**Empty file** (0 B).

---

## Page 32 — `src/adam_core/alembic.ini` (lines 1–9)

```ini
# L'URL de la BDD est injectée via variables d'environnement dans env.py

[alembic]
script_location = %(here)s/migrations
version_locations = %(here)s/migrations/versions
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
timezone = UTC
# L'URL réelle est lue dans env.py via os.getenv()
sqlalchemy.url = placeholder
```

---

## Page 33 — `src/adam_worker/src/` (directory listing)

**No code.** Contents:
- `consensus_worker.py`

---

## Page 34 — `src/adam_worker/src/consensus_worker.py` (lines 1–32)

```python
"""
Consensus Worker retry des documents en attente de résolution.

Tourne périodiquement et relance try_resolve sur les documents
qui ont atteint required_operators jobs submitted mais ne sont
pas encore VALIDATED (echec background task ou conflit non resolu).

Sprint 2 : logique de polling implementee, a refiner dans la Sprint 3
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
    Cherche tous les documents PENDING_CONSENSUS et tente de resoudre
    leur consensus.

    Idempotent : try_resolve gere les gardes internes (count, already validated).
    """
    async with get_async_session() as db:
        pending = (
```

---

## Page 35 — `src/adam_worker/src/consensus_worker.py` (lines 21–54)

```python
logger = get_logger(__name__)

async def run_pending_consensus() -> None:
    """
    Cherche tous les documents PENDING_CONSENSUS et tente de resoudre
    leur consensus.

    Idempotent : try_resolve gere les gardes internes (count, already validated).
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

# TODO Sprint 3 : brancher dans le scheduler (à definir)
```

---

## Page 36 — `scripts/` (directory listing)

**No code.** Contents:
| File | Last commit |
|---|---|
| `form_demo_v0.3.json` | chore(scripts): add seed, checks and connection test scripts |
| `download_swagger.ps1` | chore(scripts): add seed, checks and connection test scripts |
| `run-checks.ps1` | chore(scripts): add seed, checks and connection test scripts |
| `run_dev.py` | Sprint 2 : API Labellisation complète |
| `seed.py` | chore(scripts): add seed, checks and connection test scripts |
| `test_connection.py` | chore(scripts): add seed, checks and connection test scripts |

---

## Pages 37–51 — `scripts/form_demo_v0.3.json`

> **Note:** Tab titles vary across screenshots (`v0.1`, `v0.3`, `v1.1`, `v03`, `v3.3`) but the directory listing (page 36) confirms the canonical filename is **`form_demo_v0.3.json`**.

### Page 37 (lines 1–28)

```json
{
  "format_version": "0.3",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "coordinate_unit": "pixel",
  "page_count": 8,
  "pages": [
    {
      "page_number": 1,
      "width": 0,
      "height": 0,
      "sections": [
        {
          "id": "eligibilite",
          "label": "Eligibilité - section démo",
          "kv_pairs": [
            {
              "group_id": "Demandeur",
              "id": "eligibilite.ei_oui",
              "label": "Entreprise individuelle - Oui",
              "value": {
                "type": "boolean",
                "value": false,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            },
            {
              "group_id": "Demandeur",
              "id": "eligibilite.ei_non"
```

### Page 38 (lines 27–65)

```json
            {
              "group_id": "Demandeur",
              "id": "eligibilite.ei_non",
              "label": "Entreprise individuelle - Non",
              "value": {
                "type": "boolean",
                "value": true,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            },
            {
              "group_id": "Demandeur",
              "id": "eligibilite.dette_pro_oui",
              "label": "Dettes professionnelles - Oui",
              "value": {
                "type": "boolean",
                "value": false,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            },
            {
              "group_id": "Demandeur",
              "id": "eligibilite.dette_pro_non",
              "label": "Dettes professionnelles - Non",
              "value": {
                "type": "boolean",
                "value": true,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            },
            {
              "group_id": "Co-Demandeur",
              "id": "eligibilite.ei_oui",
              "label": "Entreprise individuelle - Oui",
              "value": {
                "type": "boolean",
```

### Page 39 (lines 64–102)

```json
                "value": {
                  "type": "boolean",
                  "value": false,
                  "polygon": [0,0,0,0,0,0,0,0],
                  "confidence": 1.0
                }
              },
              {
                "group_id": "Co-Demandeur",
                "id": "eligibilite.ei_non",
                "label": "Entreprise individuelle - Non",
                "value": {
                  "type": "boolean",
                  "value": true,
                  "polygon": [0,0,0,0,0,0,0,0],
                  "confidence": 1.0
                }
              },
              {
                "group_id": "Co-Demandeur",
                "id": "eligibilite.dette_pro_oui",
                "label": "Dettes professionnelles - Oui",
                "value": {
                  "type": "boolean",
                  "value": false,
                  "polygon": [0,0,0,0,0,0,0,0],
                  "confidence": 1.0
                }
              },
              {
                "group_id": "Co-Demandeur",
                "id": "eligibilite.dette_pro_non",
                "label": "Dettes professionnelles - Non",
                "value": {
                  "type": "boolean",
                  "value": true,
                  "polygon": [0,0,0,0,0,0,0,0],
                  "confidence": 1.0
                }
```

### Page 40 (lines 99–137)

```json
                "value": true,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            }
          ]
        }
      ]
    },
    {
      "page_number": 2,
      "width": 0,
      "height": 0,
      "sections": [
        {
          "id": "demandeur",
          "label": "Demandeur",
          "kv_pairs": [
            {
              "id": "demandeur.civilite_monsieur",
              "label": "Monsieur",
              "value": {
                "type": "boolean",
                "value": true,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            },
            {
              "id": "demandeur.civilite_madame",
              "label": "Madame",
              "value": {
                "type": "boolean",
                "value": false,
                "polygon": [0,0,0,0,0,0,0,0],
                "confidence": 1.0
              }
            },
            {
```

### Page 41 (lines 132–170)

```json
              "value": false,
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "id": "demandeur.nom",
            "label": "Nom",
            "value": {
              "type": "text",
              "text": "NOM01",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "id": "demandeur.prenoms",
            "label": "Prénoms",
            "value": {
              "type": "text",
              "text": "P01",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "id": "demandeur.date_naissance",
            "label": "Date de naissance",
            "value": {
              "type": "date",
              "raw_text": "04/09/1988",
              "value": "1988-09-04",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          }
        ]
      },
      {
```

### Page 42 (lines 163–201)

```json
              "value": "1988-09-04",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          }
        ]
      },
      {
        "id": "co_demandeur",
        "label": "Co-demandeur",
        "kv_pairs": [
          {
            "id": "co_demandeur.nom",
            "label": "Nom",
            "value": {
              "type": "text",
              "text": "NOM02",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "id": "co_demandeur.date_naissance",
            "label": "Date de naissance",
            "value": {
              "type": "date",
              "raw_text": "07/07/1983",
              "value": "1983-07-07",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          }
        ]
      },
      {
        "id": "coordonnees_personnelles",
        "label": "Coordonnées personnelles",
        "kv_pairs": [
          {
```

### Page 43 (lines 192–230)

```json
                "confidence": 1.0
              }
            }
          }
        ]
      },
      {
        "id": "coordonnees_personnelles",
        "label": "Coordonnées personnelles",
        "kv_pairs": [
          {
            "group_id": "demandeur",
            "id": "coordonnees_personnelles.telephone",
            "label": "Téléphone demandeur",
            "value": {
              "type": "text",
              "text": "0601020304",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "group_id": "co_demandeur",
            "id": "coordonnees_personnelles.telephone",
            "label": "Téléphone co-demandeur",
            "value": {
              "type": "text",
              "text": "0605060708",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          }
        ]
      }
    ],
    {
      "page_number": 3,
      "width": 0,
      "height": 0,
```

### Page 44 (lines 221–259)

```json
        }
      ]
    }
  ]
},
{
  "page_number": 3,
  "width": 0,
  "height": 0,
  "sections": [
    {
      "id": "situation_familiale",
      "label": "Situation familiale",
      "kv_pairs": [
        {
          "id": "situation_familiale.marie",
          "label": "Marié(e)",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.pacse",
          "label": "PACSé(e)",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.concubin",
          "label": "Concubinage",
          "value": {
```

### Page 45 (lines 255–295)

```json
        },
        {
          "id": "situation_familiale.concubin",
          "label": "Concubinage",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.celibataire",
          "label": "Célibataire",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.separe",
          "label": "Séparé(e)",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.divorce",
          "label": "Divorcé(e)",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
```

### Page 46 (lines 282–320)

```json
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.divorce",
          "label": "Divorcé(e)",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "id": "situation_familiale.veuf",
          "label": "Veuf / Veuve",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        }
      ]
    },
    {
      "id": "personnes_domicile",
      "label": "Personnes au domicile",
      "kv_pairs": [
        {
          "group_id": "enfant_1",
          "id": "personnes_domicile.date_naissance",
          "label": "Date de naissance",
          "value": {
            "type": "date",
            "raw_text": "01/05/2000",
            "value": "2000-05-01",
            "polygon": [0,0,0,0,0,0,0,0],
```

### Page 47 (lines 313–351)

```json
        {
          "group_id": "enfant_1",
          "id": "personnes_domicile.date_naissance",
          "label": "Date de naissance",
          "value": {
            "type": "date",
            "raw_text": "01/05/2000",
            "value": "2000-05-01",
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "enfant_1",
          "id": "personnes_domicile.a_charge",
          "label": "À charge",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "enfant_1",
          "id": "personnes_domicile.garde_alternee",
          "label": "Garde alternée",
          "value": {
            "type": "boolean",
            "value": false,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "enfant_1",
          "id": "personnes_domicile.droit_de_visite",
          "label": "Droit de visite",
          "value": {
```

### Page 48 (lines 340–378)

```json
            "value": {
              "type": "boolean",
              "value": false,
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "group_id": "enfant_1",
            "id": "personnes_domicile.droit_de_visite",
            "label": "Droit de visite",
            "value": {
              "type": "boolean",
              "value": true,
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "group_id": "enfant_2",
            "id": "personnes_domicile.date_naissance",
            "label": "Date de naissance",
            "value": {
              "type": "date",
              "raw_text": "01/05/2002",
              "value": "2002-05-01",
              "polygon": [0,0,0,0,0,0,0,0],
              "confidence": 1.0
            }
          },
          {
            "group_id": "enfant_3",
            "id": "personnes_domicile.date_naissance",
            "label": "Date de naissance",
            "value": {
              "type": "date",
              "raw_text": "08/10/2006",
              "value": "2006-10-08",
              "polygon": [0,0,0,0,0,0,0,0],
```

### Page 49 (lines 370–407)

```json
        },
        {
          "group_id": "enfant_3",
          "id": "personnes_domicile.date_naissance",
          "label": "Date de naissance",
          "value": {
            "type": "date",
            "raw_text": "08/10/2006",
            "value": "2006-10-08",
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "autre_1",
          "id": "personnes_domicile.date_naissance",
          "label": "Date de naissance",
          "value": {
            "type": "date",
            "raw_text": "01/05/1940",
            "value": "1940-05-01",
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "autre_2",
          "id": "personnes_domicile.date_naissance",
          "label": "Date de naissance",
          "value": {
            "type": "date",
            "raw_text": "01/05/1970",
            "value": "1970-05-01",
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        }
      ]
```

### Page 50 (lines 395–432)

```json
        }
      },
      {
        "group_id": "autre_2",
        "id": "personnes_domicile.date_naissance",
        "label": "Date de naissance",
        "value": {
          "type": "date",
          "raw_text": "01/05/1970",
          "value": "1970-05-01",
          "polygon": [0,0,0,0,0,0,0,0],
          "confidence": 1.0
        }
      }
    ],
    {
      "id": "situation_logement",
      "label": "Situation logement",
      "kv_pairs": [
        {
          "group_id": "demandeur",
          "id": "situation_logement.locataire",
          "label": "Locataire",
          "value": {
            "type": "boolean",
            "value": true,
            "polygon": [0,0,0,0,0,0,0,0],
            "confidence": 1.0
          }
        },
        {
          "group_id": "demandeur",
          "id": "situation_logement.procedure_expulsion",
          "label": "Procédure d'expulsion",
          "value": {
```

### Page 51 (lines 428–466, truncated)

```json
    {
      "group_id": "demandeur",
      "id": "situation_logement.procedure_expulsion",
      "label": "Procédure d'expulsion",
      "value": {
        "type": "boolean",
        "value": true,
        "polygon": [0,0,0,0,0,0,0,0],
        "confidence": 1.0
      }
    },
    {
      "group_id": "co_demandeur",
      "id": "situation_logement.locataire",
      "label": "Locataire",
      "value": {
        "type": "boolean",
        "value": true,
        "polygon": [0,0,0,0,0,0,0,0],
        "confidence": 1.0
      }
    },
    {
      "group_id": "co_demandeur",
      "id": "situation_logement.procedure_expulsion",
      "label": "Procédure d'expulsion",
      "value": {
        "type": "boolean",
        "value": true,
        "polygon": [0,0,0,0,0,0,0,0],
        "confidence": 1.0
      }
    },
    {
      "id": "situation_logement_demandeur2",
      ...
    }
```

---

## Summary index

| Pages | File | Type |
|---|---|---|
| 01–02 | `src/adam_core/models/ocr_result.py` | Python model |
| 03–04 | `src/adam_core/models/organisation.py` | Python model |
| 05–07 | `src/adam_core/models/project.py` | Python model |
| 08–10 | `src/adam_core/models/user.py` | Python model |
| 11–12 | `src/adam_core/models/user_project.py` | Python model |
| 13 | `src/adam_core/static/` | Directory (`favicon.ico`) |
| 14 | `src/adam_core/utils/` | Directory listing |
| 15 | `src/adam_core/utils/__init__.py` | Empty |
| 16–18 | `src/adam_core/utils/exceptions.py` | Python utils |
| 19–20 | `src/adam_core/utils/logging.py` | Python utils |
| 21–23 | `src/adam_core/utils/volumetry.py` | Python utils |
| 24–30 | `src/adam_core/README.md` | Markdown docs |
| 31 | `src/adam_core/__init__.py` | Empty |
| 32 | `src/adam_core/alembic.ini` | Config |
| 33 | `src/adam_worker/src/` | Directory listing |
| 34–35 | `src/adam_worker/src/consensus_worker.py` | Python worker |
| 36 | `scripts/` | Directory listing |
| 37–51 | `scripts/form_demo_v0.3.json` | JSON (partial, pages 4–8 of 8) |

### Ambiguities to resolve when recreating

1. **`user.py` lazy loading:** page 09 shows `lazy="noload"`, page 10 shows `lazy="selectin"` — likely different commits; README says `noload`.
2. **`project.py` organisation relationship:** commented out on page 07, active on page 06.
3. **`form_demo_v0.3.json`:** file continues beyond page 51 (pages 4–8 of 8 declared; only ~page 3–4 fully captured).
4. **Scripts not shown:** `run_dev.py`, `seed.py`, `test_connection.py`, `download_swagger.ps1`, `run-checks.ps1` are listed but not photographed in this PDF.

[REDACTED]