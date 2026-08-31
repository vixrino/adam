"""Application FastAPI ADAM."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from adam_api.core.config import API_PREFIX, settings
from adam_api.core.security import install_jwt_middleware
from adam_api.dependencies.auth import get_caller, require_service
from adam_api.routers.admin import router as admin_router
from adam_api.routers.datasets import router as datasets_router
from adam_api.routers.document_fields import router as document_fields_router
from adam_api.routers.documents import router as documents_router
from adam_api.routers.files import router as files_router
from adam_api.routers.jobs import router as jobs_router
from adam_api.routers.ocr import router as ocr_router
from adam_api.routers.organisations import router as orgs_router
from adam_api.routers.projects import router as projects_router
from adam_api.routers.schemas import router as schemas_router
from adam_api.routers.users import router as users_router
from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.exceptions import http_exception_handler
from adam_core.utils.logging import setup_logging

STATIC_DIR = Path(__file__).resolve().parent / "static"

#: /health et /db-check restent a la racine : ce sont des sondes
#: d'infrastructure, elles ne suivent pas le versionnement de l'API.
PREFIX = API_PREFIX


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)
    yield


app = FastAPI(title=settings.api_title, version=settings.app_version, lifespan=lifespan)
app.add_exception_handler(Exception, http_exception_handler)

# ORDRE CRITIQUE : Starlette place le dernier middleware ajoute en position la plus
# externe. CORS doit rester externe par rapport a exa-pie, sinon les preflights
# OPTIONS (depourvus d'en-tete Authorization) sont rejetes en 400 et le front ne
# peut plus appeler l'API. Ne pas deplacer cet appel apres l'ajout de CORS.
install_jwt_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Image-Dpi"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routes IHM : un utilisateur resolu, dont get_db derive le scope de session.
app.include_router(admin_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(orgs_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(users_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(projects_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(schemas_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(datasets_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(documents_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
# Les champs sont une sous-ressource des documents : meme prefixe, meme
# dependance. Le worker de pre-alimentation s'y presente comme un service, ce
# que get_caller resout aussi bien qu'un utilisateur.
app.include_router(document_fields_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(jobs_router, prefix=PREFIX, dependencies=[Depends(get_caller)])

# Routes machine : reservees aux services internes, jamais appelees par l'IHM.
app.include_router(files_router, prefix=PREFIX, dependencies=[Depends(require_service)])
app.include_router(ocr_router, prefix=PREFIX, dependencies=[Depends(require_service)])


def _add_binary_format_to_file_uploads(schema: Dict[str, Any]) -> None:
    """Swagger UI n'affiche le bouton de selection de fichier que si le champ
    porte `format: binary` (convention OpenAPI 3.0). Pydantic v2/FastAPI
    genere `contentMediaType` (convention OpenAPI 3.1) pour les UploadFile,
    que Swagger UI ne reconnait pas comme un champ fichier : sans ce patch,
    `files` s'affiche comme un simple tableau de chaines editable a la main."""
    for component in schema.get("components", {}).get("schemas", {}).values():
        for prop in component.get("properties", {}).values():
            target = prop.get("items", prop)
            if target.get("contentMediaType") == "application/octet-stream":
                target["format"] = "binary"


def custom_openapi() -> Dict[str, Any]:
    if app.openapi_schema is None:
        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        _add_binary_format_to_file_uploads(app.openapi_schema)
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/db-check")
async def db_check() -> JSONResponse:
    from sqlalchemy import text
    from adam_core.db.session import get_async_session

    try:
        async with get_async_session() as db:
            await db.execute(text("SELECT 1"))
        return JSONResponse({"database": "ok"})
    except Exception as exc:  # pylint: disable=broad-except
        return JSONResponse({"database": "error", "detail": str(exc)}, status_code=503)
