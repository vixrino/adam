# ADAM — Transcription Report

> **Note :** les captures d'écran sources (`_screenshots/`) ont été supprimées pour anonymisation.

**Generated:** 2026-06-24  
**Sources:** lots PDF transcrits *(supprimés)*  
**PNG output:** *(supprimé)*  
**Supplementary:** *(supprimé)*

---

## Summary

| PDF | Pages | Code files transcribed | Directory-only pages |
|-----|-------|------------------------|----------------------|
| Pds6 | 41 | 12 files (partial) | 8 |
| Pds7 | 41 | 7 router files (partial) | 0 |

**Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic v2, PostgreSQL, Hatchling  
**Packages:** `src/adam_core`, `src/adam_api`, `src/adam_worker`  
**Active branch:** `develop`

---

# PDS6 — Project structure & configuration (41 pages)

---

## Page 1 — `README.md` (root)

**Screenshot:** `all_pages/Pds6-01.png`  
**Type:** Documentation (no line numbers)

```markdown
# ADAM - Annotation et Données Automatisées

> Branche `master` ne contient pas encore de release stable. Le développement actif se trouve sur la branche `develop`.

## Accéder au code

git clone https://git.example.com/example-org/adam/adam.git
cd adam
git checkout develop

## Branches

| Branche | Rôle |
| main | Releases stables uniquement |
| develop | **Développement actif** |
| feature/* | Nouvelles fonctionnalités |
| fix/* | Corrections de bugs |

## Contact

Développeur - dev@example.com
```

---

## Page 2 — Repository root tree

**Screenshot:** `all_pages/Pds6-02.png`  
**Type:** Directory listing (no code)

| Name | Last commit |
|------|-------------|
| scripts/ | Sprint 2 : API Labellisation complète |
| src/ | Sprint 2 : API Labellisation complète |
| tests/ | Sprint 2 : API Labellisation complète |
| .env.template | chore(repo): init structure |
| .gitignore | chore(config): upgrade Python 3.12 |
| CONTRIBUTING.md | chore(repo): init structure |
| README.md | initial commit |
| pyproject.toml | Sprint 2 : API Labellisation complète |

---

## Page 3 — `pyproject.toml` lines 1–36

**Screenshot:** `all_pages/Pds6-03.png`

```toml
1  [build-system]
2  requires = ["hatchling"]
3  build-backend = "hatchling.build"
4
5  # Project
6  [project]
7  name = "adam"
8  version = "0.1.0"
9  description = "ADAM - Annotation et Donnees Automatisees"
10 authors = [
11   {name = "Equipe ADAM", email = "dev@example.com"}
12 ]
13 readme = "README.md"
14 license = {text = "Proprietary"}
15 requires-python = ">=3.12"
16 keywords = ["tests automatises", "ocr", "labellisation", "annotation"]
17 classifiers = [
18   "Programming Language :: Python",
19   "Programming Language :: Python :: 3",
20   "Programming Language :: Python :: 3.12",
21   "Private :: Do Not Upload",
22 ]
23 dependencies = [
24   # ORM + DB
25   "sqlalchemy[asyncio]>=2.0.32",
26   "alembic>=1.13.2",
27   "asyncpg>=0.29.0",
28   "psycopg2-binary>=2.9.9",
29   # API
30   "fastapi>=0.111.0",
31   "uvicorn[standard]>=0.30.3",
32   "python-multipart>=0.0.9",
33   "aiofiles>=23.2.1",
34   # Config
35   "pydantic>=2.7.4",
36   "pydantic-settings>=2.3.4",
```

---

## Page 4 — `pyproject.toml` lines 37–74

**Screenshot:** `tree_pages/pds6-04.png`

```toml
37    # Auth
38    "python-jose[cryptography]>=3.3.0",
39    # Interne
40    "exa-pie>=1.4.0",
41    "exa-logger>=2.3.0",
42 ]
43
44 [project.optional-dependencies]
45 dev = [
46   # Tests
47   "pytest>=8.2.0",
48   "pytest-asyncio>=0.23.0",
49   "pytest-cov>=5.0.0",
50   "httpx>=0.27.0",
51   # Qualite
52   "black>=24.0.0",
53   "isort>=5.13.0",
54   "pylint>=3.2.0",
55   "bandit>=1.7.0",
56   "interrogate>=1.7.0",
57   "mypy>=1.10.0",
58 ]
59
60 [tool.hatch.build.targets.wheel]
61 packages = ["src/adam_core", "src/adam_api"]
62
63 # Black
64 [tool.black]
65 target-version = ["py312"]
66 line-length = 100
67
68 # Mypy
69 [tool.mypy]
70 python_version = "3.12"
71 ignore_missing_imports = true
72 exclude = ["migrations", "scripts"]
73 plugins = ["sqlalchemy.ext.mypy.plugin"]
74
```

---

## Page 5 — `pyproject.toml` lines 75–113

**Screenshot:** `tree_pages/pds6-05.png`

```toml
75  # Bandit (securite)
76  [tool.bandit]
77  exclude_dirs = ["tests", "scripts"]
78  tests = ["B201", "B301"]
79  skips = ["B101", "B601", "B607"]
80
81  # Interrogate (docstrings)
82  [tool.interrogate]
83  ignore-init-method = true
84  ignore-init-module = false
85  ignore-magic = false
86  ignore-semiprivate = false
87  ignore-private = false
88  ignore-property-decorators = false
89  ignore-module = false
90  ignore-nested-functions = false
91  ignore-nested-classes = true
92  ignore-setters = false
93  fail-under = 95
94  exclude = ["setup.py", "docs", "build", "scripts"]
95  ignore-regex = ["^get$", "^mock_.*", ".*BaseClass.*"]
96  verbose = 0
97  quiet = false
98  color = true
99  generate-badge = "."
100 badge-format = "svg"
101
102 # Pylint
103 [tool.pylint.master]
104 fail-under = 9.0
105 ignore-paths = [
106     "src/adam_core/models",
107     "src/adam_core/migrations",
108 ]
109
110 [tool.pylint.messages_control]
111 max-line-length = 100
112 disable = [
113     "missing-docstring",
```

> **GAP:** Lines 114–122 not visible between pages 5 and 6.

---

## Page 6 — `pyproject.toml` lines 123–156

**Screenshot:** `tree_pages/pds6-06.png`

```toml
123         "duplicate-code",
124     ]
125
126 [tool.pylint.design]
127 max-returns = 8
128
129 [tool.pylint.basic]
130 good-names = ["db", "id", "e", "f", "_engine", "_async_session_factory"]
131
132 # Coverage
133 [tool.coverage.run]
134 source = ["src"]
135 omit = [
136     "*/enums/*",
137     "*/migrations/*",
138     "*/models/*",
139     "scripts/*",
140     "src/adam_core/db/base.py",
141     "src/adam_core/utils/volumetry.py",
142     "src/adam_api/main.py",
143     "src/adam_api/dependencies/db.py",
144 ]
145
146 [tool.coverage.report]
147 fail_under = 80
148 show_missing = true
149 skip_empty = true
150
151 # Pytest
152 [tool.pytest.ini_options]
153 asyncio_mode = "auto"
154 testpaths = ["tests"]
155 python_files = ["test_*.py"]
156 addopts = "--tb=short"
```

---

## Page 7 — `README.md` (duplicate of page 1)

**Screenshot:** `tree_pages/pds6-07.png` — same content as Page 1.

---

## Page 8 — `CONTRIBUTING.md` (branches + commit convention)

**Screenshot:** `tree_pages/pds6-08.png`

```markdown
# Contribuer au projet ADAM

## Branches
- main <- production, protegee, merge via MR uniquement
- develop <- integration continue, base de toutes les branches
- feature/xxx <- nouvelle fonctionnalite (depuis develop)
- fix/xxx <- correction de bug (depuis develop)

## Convention de commits
Format: <type>(<scope>): <description courte>

| Type | Usage |
| feat | Nouvelle fonctionnalite |
| fix | Correction de bug |
| refactor | Refactoring sans changement fonctionnel |
| test | Ajout ou modification de tests |
| docs | Documentation uniquement |
| chore | Outillage, config, dependances |
| migration | Migration Alembic |

Exemples :
```

---

## Page 9 — `CONTRIBUTING.md` (examples + quality gates)

**Screenshot:** `tree_pages/pds6-09.png`

```
feat(orm): add FieldSpec model with section_id and polygon constraint
feat(api): add GET /documents/{id}/fields/by-section endpoint
fix(session): handle special characters in POSTGRES_PASSWORD via URL.create
migration: init tables labellisation
chore(config): add pylint and coverage quality gates
docs(adam_core): add README with Alembic workflow

## Quality Gates
Avant tout merge sur develop :

| Metrique | Seuil |
| Pylint score | >= 9.0 / 10 |
| Couverture de tests | >= 80% |
| Alembic migrations | alembic upgrade head sans erreur |
| API startup | uvicorn demarre sans erreur |

Commandes de verification :
python -m pylint src\adam_core\ src\adam_api\
python -m pytest --cov=src --cov-report=term-missing
```

---

## Page 10 — `CONTRIBUTING.md` (workflow)

**Screenshot:** `tree_pages/pds6-10.png`

```bash
cd src\adam_core && python -m alembic upgrade head
```

```
## Workflow Sprint
1. Creer la branche : git checkout -b feature/ma-feature develop
2. Developper + committer au fil de l'eau
3. Verifier les quality gates localement
4. Pousser : git push origin feature/ma-feature
5. Ouvrir une Merge Request vers develop
6. Review + merge
```

---

## Page 11 — `.gitignore` lines 1–36

**Screenshot:** `tree_pages/pds6-11.png`

```gitignore
1   # Byte-compiled / optimized / DLL files
2   __pycache__/
3   *.py[cod]
4   *$py.class
5   # C extensions
6   *.so
7   # Distribution / packaging
8   .Python
9   build/
10  out/
11  develop-eggs/
12  dist/
13  downloads/
14  eggs/
15  .eggs/
16  lib/
17  lib64/
18  parts/
19  sdist/
20  var/
21  wheels/
22  share/python-wheels/
23  *.egg-info/
24  .installed.cfg
25  *.egg
26  MANIFEST
27  # PyInstaller
28  *.manifest
29  *.spec
30  # Installer logs
```

---

## Page 12 — `.gitignore` lines 36–74

**Screenshot:** `tree_pages/pds6-12.png`

```gitignore
36  # Installer logs
37  pip-log.txt
38  pip-delete-this-directory.txt
39  # Unit test / coverage reports
40  htmlcov/
41  .tox/
42  .nox/
43  .coverage
44  .coverage.*
45  .cache
46  nosetests.xml
47  coverage.xml
48  *.cover
49  .hypothesis/
50  .pytest_cache/
51  # Translations
52  *.mo
53  *.pot
54  # Django stuff:
55  *.log
56  local_settings.py
57  db.sqlite3
58  # Flask stuff:
59  instance/
60  .webassets-cache
61  # Scrapy stuff:
62  .scrapy
63  # Sphinx documentation
64  docs/_build/
65  # PyBuilder
66  target/
```

---

## Page 13 — `.gitignore` lines 72–110

**Screenshot:** `tree_pages/pds6-13.png`

```gitignore
72  # PyBuilder
73  target/
74  # Jupyter Notebook
75  .ipynb_checkpoints
76  # IPython
77  profile_default/
78  ipython_config.py
79  # pyenv
80  .python-version
81  # celery beat schedule file
82  celerybeat-schedule
83  # SageMath parsed files
84  *.sage.py
85  # Environments
86  .env
87  .venv
88  env/
89  venv/
90  ENV/
91  env.bak/
92  venv.bak/
93  # Spyder project settings
94  .spyderproject
95  .spyproject
96  # Rope project settings
97  .ropeproject
98  # mkdocs documentation
99  /site
100 # mypy
```

---

## Page 14 — `.gitignore` lines 92–124

**Screenshot:** `tree_pages/pds6-14.png`

```gitignore
92  .env
93  .venv
94  env/
95  venv/
96  ENV/
97  env.bak/
98  venv.bak/
99  # Spyder project settings
100 .spyderproject
101 .spyproject
102 # Rope project settings
103 .ropeproject
104 # mkdocs documentation
105 /site
106 # mypy
107 .mypy_cache/
108 .dmypy.json
109 dmypy.json
110 # Pyre type checker
111 .pyre/
112 #pycharm
113 .idea/
114 # FastAPI swagger
115 src/adam_core/static/swagger-ui-bundle.js
116 src/adam_core/static/swagger-ui.css
```

---

## Page 15 — `.env.template` lines 1–37

**Screenshot:** `tree_pages/pds6-15.png`

```dotenv
1  # Environnements
2  # Valeurs : dev | staging | prod
3  APP_ENV=dev
4  APP_NAME=ADAM
5  APP_VERSION=0.1.0
6
7  # BDD
8  POSTGRES_USER=adam
9  POSTGRES_DB=adam_db
10 POSTGRES_HOST=localhost
11 POSTGRES_PORT=5432
12 POSTGRES_PASSWORD=PASSWORD
13 # DATABASE_URL=postgresql+asyncpg://adam:adam_dev_password@localhost:5432/adam_db
14
15 # API FastAPI
16 API_HOST=0.0.0.0
17 API_PORT=8000
18 API_WORKERS=1
19 API_TITLE="ADAM API"
20 API_CORS_ORIGINS=http://localhost:4200
21
22 # Auth
23 API_DISABLE_JWT_VALIDATION=true
24
25 # Secret JWT
26 JWT_SECRET_KEY=changeme_use_a_strong_random_secret_in_prod
27 JWT_ALGORITHM=HS256
28 JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
29
30 # Stockage fichiers (PVC)
31 PVC_MOUNT_PATH=./data/pvc
32
33 # Logging
34 LOG_LEVEL=DEBUG
35 LOG_FORMAT=json
36
37 # BDD (partial/cut off)
```

---

## Page 16 — `.env.template` lines 8–40

**Screenshot:** `all_pages/Pds6-16.png`

```dotenv
8  POSTGRES_USER=adam
9  POSTGRES_DB=adam_db
10 POSTGRES_HOST=localhost
11 POSTGRES_PORT=5432
12 POSTGRES_PASSWORD=PASSWORD
13 # DATABASE_URL=postgresql+asyncpg://adam:adam_dev_password@localhost:5432/adam_db
14
15 # API FastAPI
16 API_HOST=0.0.0.0
17 API_PORT=8000
18 API_WORKERS=1
19 API_TITLE="ADAM API"
20 API_CORS_ORIGINS=http://localhost:4200
21
22 # Auth
23 API_DISABLE_JWT_VALIDATION=true
24
25 # Secret JWT
26 JWT_SECRET_KEY=changeme_use_a_strong_random_secret_in_prod
27 JWT_ALGORITHM=HS256
28 JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
29
30 # Stockage fichiers (PVC)
31 PVC_MOUNT_PATH=./data/pvc
32
33 # Logging
34 LOG_LEVEL=DEBUG
35 LOG_FORMAT=json
36
37 # OCR
38 OCR_MOCK_ENABLED=true
39 OCR_MOCK_CONFIDENCE=0.95
40 OCR_TIMEOUT_SECONDS=30
```

---

## Page 17 — `tests/` directory

**Screenshot:** `all_pages/Pds6-17.png` — Directory: `integration/`, `unit/`, `__init__.py`

---

## Page 18 — `tests/integration/` directory

**Screenshot:** `all_pages/Pds6-18.png` — Only `__init__.py`

---

## Page 19 — `tests/unit/` directory listing

**Screenshot:** `all_pages/Pds6-19.png`

Files: `__init__.py`, `test_exceptions.py`, `test_interface_contract.py`, `test_logging.py`, `test_router_datasets.py`, `test_router_documents.py`, `test_router_files.py`, `test_router_jobs.py`, `test_router_ocr.py`, `test_router_organisations.py`, `test_router_projects.py`, `test_router_schemas.py`, `test_router_users.py`, `test_session.py`

---

## Page 20 — `tests/unit/test_exceptions.py` lines 1–35

**Screenshot:** `all_pages/Pds6-20.png`

```python
1   """
2   Tests unitaires - adam_core/utils/exceptions.py
3   """
4   import pytest
5   from fastapi import HTTPException
6   from unittest.mock import MagicMock, AsyncMock
7   from fastapi.testclient import TestClient
8   from fastapi import FastAPI
9
10  from adam_core.utils.exceptions import (
11      _name,
12      raise_not_found,
13      raise_already_archived,
14      raise_not_archived,
15      raise_already_exists,
16      raise_conflict,
17      raise_unprocessable,
18      http_exception_handler,
19      NOT_FOUND,
20      ALREADY_ARCHIVED,
21      NOT_ARCHIVED,
22      ALREADY_EXISTS,
23  )
24
25  # Fixtures
26
27  class FakeModel:
28      __tablename__ = "organisation"
29
30  class FakeModelNoTablename:
31      __name__ = "Project"
```

---

## Page 21 — `tests/unit/test_exceptions.py` lines 26–64

**Screenshot:** `all_pages/Pds6-21.png`

```python
26  # Fixtures
27  class FakeModel:
28      __tablename__ = "organisation"
29  class FakeModelNoTablename:
30      __name__ = "Project"
31
32  # _name
33  class TestName:
34      def test_uses_tablename_when_present(self) -> None:
35          assert _name(FakeModel) == "Organisation"
36      def test_falls_back_to_class_name(self) -> None:
37          assert _name(FakeModelNoTablename) == "Fakemodelnotablename"
38      def test_capitalizes_result(self) -> None:
39          class Lower:
40              __tablename__ = "user_project"
41          assert _name(Lower) == "User_project"
42
43  # raise_not_found
44  class TestRaiseNotFound:
45      def test_raises_404(self) -> None:
46          with pytest.raises(HTTPException) as exc_info:
47              raise_not_found(FakeModel)
48          assert exc_info.value.status_code == 404
```

---

## Page 22 — `src/` directory

**Screenshot:** `all_pages/Pds6-22.png` — `adam_api/`, `adam_core/`, `adam_worker/src/`

---

## Page 23 — `src/adam_api/` directory

**Screenshot:** `all_pages/Pds6-23.png` — `core/`, `dependencies/`, `routers/`, `services/`, `__init__.py`, `main.py`

---

## Page 24 — `src/adam_api/core/` directory

**Screenshot:** `all_pages/Pds6-24.png` — `__init__.py`, `config.py`

---

## Page 25 — `src/adam_api/core/config.py` lines 1–37

**Screenshot:** `all_pages/Pds6-25.png`

```python
1   """
2   Settings specifiques a l'API ADAM.
3   """
4   from functools import lru_cache
5   from typing import List
6   from adam_core.core.config import CoreSettings
7
8   class Settings(CoreSettings):
9       # API
10      api_host: str
11      api_port: int
12      api_version: str
13      api_title: str
14      api_cors_origins: str
15      # Auth IHM
16      api_disable_jwt_validation: bool
17      # Auth service machine
18      internal_auth_enabled: bool
19      internal_api_key: str
20      # Stockage
21      pvc_mount_path: str
22      # OCR
23      ocr_mock_enabled: bool
24      ocr_mock_confidence: float
25      ocr_timeout_seconds: int
26      # Computed
27      @property
28      def cors_origins(self) -> List[str]:
```

---

## Page 26 — `src/adam_api/core/config.py` lines 14–47

**Screenshot:** `all_pages/Pds6-26.png`

```python
14      api_host: str
15      api_port: int
16      api_version: str
17      api_title: str
18      api_cors_origins: str
19      # Auth IHM
20      api_disable_jwt_validation: bool
21      # Auth service machine
22      internal_auth_enabled: bool
23      internal_api_key: str
24      # Stockage
25      pvc_mount_path: str
26      # OCR
27      ocr_mock_enabled: bool
28      ocr_mock_confidence: float
29      ocr_timeout_seconds: int
30      @property
31      def cors_origins(self) -> List[str]:
32          return [o.strip() for o in self.api_cors_origins.split(",")]
33
34  @lru_cache
35  def get_settings() -> Settings:
36      return Settings()  # type: ignore[call-arg]
37
38  settings = get_settings()
```

---

## Page 27 — `src/adam_api/dependencies/auth.py` lines 1–29

**Screenshot:** `all_pages/Pds6-27.png`

```python
1   """
2   Auth - Detection de l'origine de la requete.
3   Deux types d'appelants :
4       - UserCaller : IHM Angular via JWT tiers
5       - ServiceCaller : service machine via X-Internal-Token
6   En DEV :
7       - JWT bypass si API_DISABLE_JWT_VALIDATION=true -> UserCaller mock
8       - Token bypass si INTERNAL_AUTH_ENABLED=false   -> ServiceCaller mock
9   """
10  import secrets
11  from typing import Optional, Union
12  from fastapi import Depends, HTTPException
```

---

## Page 28 — `src/adam_api/dependencies/auth.py` lines 23–61

**Screenshot:** `all_pages/Pds6-28.png`

```python
26  import secrets
27  from typing import Optional, Union
28  from fastapi import Depends, HTTPException
29  from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
30  from pydantic import BaseModel
31  from adam_api.core.config import settings
32  from adam_core.utils.logging import get_logger
33  logger = get_logger(__name__)
34  _bearer = HTTPBearer(auto_error=False)
35  _api_key_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)
36
37  class UserCaller(BaseModel):
38      matricule: str
39      organisation_id: int
40  class ServiceCaller(BaseModel):
41      service_name: str
42  Caller = Union[UserCaller, ServiceCaller]
43
44  async def get_caller(
45      jwt: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
```

---

## Page 29 — `src/adam_api/dependencies/auth.py` lines 61–98

**Screenshot:** `all_pages/Pds6-29.png`

```python
61      jwt: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
62      api_key: Optional[str] = Depends(_api_key_header),
63  ) -> Caller:
64      """Detecte l'origine - IHM ou service machine. Priorite : X-Internal-Token > JWT Bearer."""
65      if api_key is not None:
66          if not settings.internal_auth_enabled:
67              logger.critical("AUTH SERVICE BYPASS actif ne jamais utiliser en production")
68              return ServiceCaller(service_name="bypass-dev")
69          if not secrets.compare_digest(api_key, settings.internal_api_key):
70              raise HTTPException(status_code=403, detail="Token service invalide")
71          return ServiceCaller(service_name="internal-service")
72      if jwt is not None:
73          if settings.api_disable_jwt_validation:
74              logger.critical("JWT BYPASS actif ne jamais utiliser en production")
75              return UserCaller(matricule="MAT00003", organisation_id=1)
76          # TODO Sprint 2 : decoder le JWT du tiers
77          raise HTTPException(status_code=501, detail="Auth JWT non implementee")
78      raise HTTPException(status_code=401, detail="Authentification requise")
79
80  async def require_user(caller: Caller = Depends(get_caller)) -> UserCaller:
81      """Restreint la route aux utilisateurs IHM uniquement."""
```

---

## Page 30 — `src/adam_api/dependencies/auth.py` lines 97–114

**Screenshot:** `all_pages/Pds6-30.png`

```python
97  async def require_user(caller: Caller = Depends(get_caller)) -> UserCaller:
98      if not isinstance(caller, UserCaller):
99          raise HTTPException(status_code=403, detail="Route reservee aux utilisateurs IHM")
100     return caller
101
102 async def require_service(caller: Caller = Depends(get_caller)) -> ServiceCaller:
103     if not isinstance(caller, ServiceCaller):
104         raise HTTPException(status_code=403, detail="Route reservee aux services internes")
105     return caller
```

---

## Page 31 — `src/adam_api/dependencies/db.py` lines 1–15

**Screenshot:** `all_pages/Pds6-31.png`

```python
1   """
2   Dependency FastAPI pour l'injection de session SQLAlchemy.
3   """
4   from collections.abc import AsyncGenerator
5   from sqlalchemy.ext.asyncio import AsyncSession
6   from adam_core.db.session import get_async_session
7
8   async def get_db() -> AsyncGenerator[AsyncSession, None]:
9       async with get_async_session() as session:
10          yield session
```

---

## Page 32 — `src/adam_api/routers/` directory

**Screenshot:** `all_pages/Pds6-32.png` — `admin.py`, `datasets.py`, `documents.py`, `files.py`, `jobs.py`, `ocr.py`, `organisations.py`, `projects.py`, `schemas.py`, `users.py`

---

## Page 33 — `src/adam_api/routers/admin.py` lines 1–18

**Screenshot:** `all_pages/Pds6-33.png`

```python
1  from typing import Any
2  from fastapi import APIRouter, HTTPException
3  from adam_api.core.config import settings
4  from adam_api.services.consensus import try_resolve
5  router = APIRouter(prefix="/documents", tags=["Documents"])
6
7  @router.post("/admin/consensus/resolve/{document_id}", include_in_schema=True)
8  async def force_resolve(document_id: int, dataset_id: int) -> dict[str, Any]:
9      if not settings.is_dev:
10         raise HTTPException(status_code=403)
11     result = await try_resolve(document_id, dataset_id)
12     return result
```

---

## Page 34 — `src/adam_api/routers/datasets.py` lines 1–36

**Screenshot:** `all_pages/Pds6-34.png`

```python
1   """Datasets - Cree par les admins metier via CLI, IHM Admin en V2."""
2   from typing import Any, Dict, List, Optional
3   from fastapi import APIRouter, Depends
4   from pydantic import BaseModel, Field
5   from sqlalchemy import select
6   from sqlalchemy.ext.asyncio import AsyncSession
7   from sqlalchemy.orm import selectinload
8   from sqlalchemy.sql.functions import count
9   from adam_api.dependencies.db import get_db
10  from adam_core.enums.ocr import OcrProvider
11  from adam_core.enums.status import DatasetStatus, DocumentStatus
12  from adam_core.models import Dataset, Document
13  from adam_core.utils.exceptions import raise_not_found, raise_unprocessable
14  router = APIRouter(prefix="/datasets", tags=["Datasets"])
15
16  class DatasetIn(BaseModel):
17      project_id: int
18      schema_id: int
19      name: str
20      description: Optional[str] = None
21      ocr_provider: str = OcrProvider.PULSAR.value
22      ocr_model_id: Optional[str] = None
23      required_operators: int = Field(default=2, ge=1, le=5)
24      ocr_job_enabled: bool = True
```

---

## Page 35 — `datasets.py` lines 36–74

**Screenshot:** `all_pages/Pds6-35.png`

```python
36      ocr_job_enabled: bool = True
37      configs: Dict[str, Any] = Field(default_factory=dict)
38  class DatasetPatch(BaseModel):
39      name: Optional[str] = None
40      description: Optional[str] = None
41      status: Optional[str] = None
42      required_operators: Optional[int] = Field(default=None, ge=1, le=5)
43      ocr_job_enabled: Optional[bool] = None
44      configs: Optional[Dict[str, Any]] = None
45
46  @router.get("", response_model=List[Dict[str, Any]])
47  async def list_datasets(project_id, status, db) -> List[Dict[str, Any]]:
48      query = select(Dataset)
49      # filters...
50      return [{"id": r.id, "name": r.name, "status": r.status, ...}]
```

---

## Page 36 — `datasets.py` lines 74–112

**Screenshot:** `all_pages/Pds6-36.png` — `get_dataset`, `get_dataset_stats` (partial)

---

## Page 37 — `datasets.py` lines 111–149

**Screenshot:** `all_pages/Pds6-37.png` — stats endpoint + `create_dataset` start

---

## Page 38 — `datasets.py` lines 141–179

**Screenshot:** `all_pages/Pds6-38.png` — `create_dataset`, `patch_dataset` start

---

## Page 39 — `datasets.py` lines 186–224

**Screenshot:** `all_pages/Pds6-39.png` — `patch_dataset`, `patch_dataset_status` start

---

## Page 40 — `datasets.py` lines 197–230

**Screenshot:** `all_pages/Pds6-40.png` — `patch_dataset_status` complete

---

## Page 41 — `src/adam_api/routers/documents.py` lines 1–35

**Screenshot:** `all_pages/Pds6-41.png`

```python
1   """Documents - GET/POST/PATCH endpoints."""
2   from typing import Any, Dict, List, Optional
3   from fastapi import APIRouter, Depends, HTTPException
4   from pydantic import BaseModel
5   from sqlalchemy import select
6   from sqlalchemy.ext.asyncio import AsyncSession
7   from sqlalchemy.orm import selectinload
8   from adam_api.dependencies.db import get_db
9   from adam_core.enums.status import DocumentFieldStatus, DocumentStatus
10  from adam_core.models import Document, DocumentField
11  from adam_core.schemas.document import DocumentOut
12  from adam_core.utils.exceptions import raise_not_found, raise_unprocessable
13  router = APIRouter(prefix="/documents", tags=["Documents"])
14
15  class DocumentIn(BaseModel):
16      dataset_id: int
17      file_id: int
18      file_name: str
19      metadata: Dict[str, Any] = {}
20  class DocumentPatch(BaseModel):
21      status: str
22      expected_current_status: Optional[str] = None
```

---

# PDS7 — API routers continued (41 pages)

---

## Page 1 — `documents.py` lines 34–72

**Screenshot:** `all_pages/Pds7-01.png`

```python
34      status: str
35      expected_current_status: Optional[str] = None
36  class DocumentFieldPatch(BaseModel):
37      resolved_value: Optional[str] = None
38      status: Optional[str] = None
39      consensus_reached: Optional[bool] = None
40
41  @router.get("", response_model=List[DocumentOut])
42  async def list_documents(dataset_id, status, limit, db) -> Any:
43      query = select(Document)
44      # filters by dataset_id, status, limit
45      return rows
46
47  @router.get("/{document_id}", response_model=Dict[str, Any])
48  async def get_document(document_id: int, view: Optional[str] = None, ...):
```

---

## Page 2 — `documents.py` lines 72–110

**Screenshot:** `all_pages/Pds7-02.png` — `get_document` full view with selectinload, pages/sections builder

---

## Page 3 — `documents.py` lines 110–148

**Screenshot:** `all_pages/Pds7-03.png` — field dict + return doc with file

---

## Page 4 — `documents.py` lines 147–185

**Screenshot:** `all_pages/Pds7-04.png` — ocr_results, pages, jobs + simple view query

---

## Page 5 — `documents.py` lines 185–223

**Screenshot:** `all_pages/Pds7-05.png` — simple return + `get_document_fields`

---

## Page 6 — `documents.py` lines 223–261

**Screenshot:** `all_pages/Pds7-06.png` — fields list + `get_document_fields_by_section`

---

## Page 7 — `documents.py` lines 261–299

**Screenshot:** `all_pages/Pds7-07.png` — by-section return + `create_document`

---

## Page 8 — `documents.py` lines 297–335

**Screenshot:** `all_pages/Pds7-08.png` — create return + `patch_document`

---

## Page 9 — `documents.py` lines 335–373

**Screenshot:** `all_pages/Pds7-09.png` — conflict 409 + `patch_document_field`

---

## Page 10 — `documents.py` lines 343–376

**Screenshot:** `all_pages/Pds7-10.png` — `patch_document_field` return

---

## Page 11 — `src/adam_api/routers/files.py` lines 1–36

**Screenshot:** `all_pages/Pds7-11.png`

```python
1   """Files - fichier physique sur PVC."""
2   router = APIRouter(prefix="/files", tags=["Files"])
3   class FileIn(BaseModel):
4       file_path: str
5       sha256_checksum: str = Field(min_length=64, max_length=64)
6       file_size_bytes: int = Field(gt=0)
7       page_count: int = Field(default=1, ge=1)
8       mime_type: str = Field(default="application/pdf")
9       storage_type: str = Field(default="pvc")
```

---

## Page 12 — `files.py` lines 35–73

**Screenshot:** `all_pages/Pds7-12.png` — `FilePatch`, `list_files`, `get_file` start

---

## Page 13 — `files.py` lines 73–111

**Screenshot:** `all_pages/Pds7-13.png` — `get_file`, `get_file_documents`, `create_file` start

---

## Page 14 — `files.py` lines 111–149

**Screenshot:** `all_pages/Pds7-14.png` — dedup logic + `patch_file` start

---

## Page 15 — `files.py` lines 140–173

**Screenshot:** `all_pages/Pds7-15.png` — `patch_file` complete

---

## Page 16 — `src/adam_api/routers/jobs.py` lines 1–35

**Screenshot:** `all_pages/Pds7-16.png`

```python
1   """Jobs - tache de labellisation par operateur."""
2   router = APIRouter(prefix="/jobs", tags=["Jobs"])
3   class JobIn(BaseModel):
4       dataset_id: int
5       document_id: int
6       agent_id: int  # TODO Sprint 3 : remplacer par caller.organisation_id
```

---

## Pages 17–25 — `jobs.py` lines 35–330

**Screenshots:** `Pds7-17` through `Pds7-25`  
Covers: `list_jobs`, `get_job`, `create_job`, `propose_field_value`, `submit_job` with consensus trigger via `background_tasks.add_task(try_resolve, ...)`

---

## Page 26 — `src/adam_api/routers/ocr.py` lines 1–36

**Screenshot:** `all_pages/Pds7-26.png`

```python
1   """Resultats OCR - GET/POST."""
2   router = APIRouter(prefix="/ocr-results", tags=["OCR"])
3   class OcrResultIn(BaseModel):
4       document_id: int
5       dataset_id: int
6       raw_json: Dict[str, Any]
7       storage_mode: str = Field(default=StorageMode.JSONB.value)
```

---

## Pages 27–31 — `ocr.py` lines 35–186

**Screenshots:** `Pds7-27` through `Pds7-31`  
Covers: list/get OCR, `post_ocr_result` with FormDocument validation, FieldSpec indexing, DocumentField creation

---

## Page 32 — `src/adam_api/routers/organisations.py` lines 1–35

**Screenshot:** `all_pages/Pds7-32.png`

```python
1   """Organisations - CRUD + archive/restore."""
2   router = APIRouter(prefix="/organisations", tags=["Organisations"])
3   class OrganisationIn(BaseModel):
4       name: str
5       slug: str = Field(pattern=r"^[a-z0-9\-]+$")
6   class OrganisationPatch(BaseModel):
```

---

## Pages 33–37 — `organisations.py` lines 34–179

**Screenshots:** `Pds7-33` through `Pds7-37`  
Covers: list, list users, create, patch, archive, restore

---

## Page 38 — `src/adam_api/routers/projects.py` lines 1–36

**Screenshot:** `all_pages/Pds7-38.png`

```python
1   """Projects - scope de travail pour datasets."""
2   router = APIRouter(prefix="/projects", tags=["Projects"])
3   class ProjectIn(BaseModel):
4       organisation_id: int
5       name: str
6       description: Optional[str] = None
7   class ProjectPatch(BaseModel):
8       name: Optional[str] = None
```

---

## Pages 39–41 — `projects.py` lines 35–147

**Screenshots:** `Pds7-39` through `Pds7-41`  
Covers: list, get, create, `add_user_to_project` (partial, line 147)

---

# Gaps & not in screenshots

- `adam_core` models, enums, migrations, `main.py`, `services/consensus.py`
- Routers: `schemas.py`, `users.py` (listed but not photographed)
- `pyproject.toml` lines 114–122 (pylint disable entries between pages)
- `documents.py` lines 149–184 (full view return block partially split across pages)
- `projects.py` lines 148+ (add_user_to_project completion, PATCH, DELETE)
- All `adam_worker` and `scripts/` content
- Test file bodies (except `test_exceptions.py` partial)

---

# File index (transcribed source files)

| File | Lines covered | PDF pages |
|------|---------------|-----------|
| README.md | full | Pds6-1,7 |
| pyproject.toml | 1-113, 123-156 | Pds6-3..6 |
| CONTRIBUTING.md | full | Pds6-8..10 |
| .gitignore | 1-124 | Pds6-11..14 |
| .env.template | 1-40 | Pds6-15,16 |
| tests/unit/test_exceptions.py | 1-64 | Pds6-20,21 |
| src/adam_api/core/config.py | 1-47 | Pds6-25,26 |
| src/adam_api/dependencies/auth.py | 1-114 | Pds6-27..30 |
| src/adam_api/dependencies/db.py | 1-15 | Pds6-31 |
| src/adam_api/routers/admin.py | 1-18 | Pds6-33 |
| src/adam_api/routers/datasets.py | 1-230 | Pds6-34..40 |
| src/adam_api/routers/documents.py | 1-376 | Pds6-41, Pds7-1..10 |
| src/adam_api/routers/files.py | 1-173 | Pds7-11..15 |
| src/adam_api/routers/jobs.py | 1-330 | Pds7-16..25 |
| src/adam_api/routers/ocr.py | 1-186 | Pds7-26..31 |
| src/adam_api/routers/organisations.py | 1-179 | Pds7-32..37 |
| src/adam_api/routers/projects.py | 1-147 | Pds7-38..41 |
