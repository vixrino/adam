"""
API NOTA

Demarrage :
    python -m uvicorn adam_api.main:app --reload
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy import text

from adam_api.core.config import settings
from adam_api.core.security import install_jwt_middleware
from adam_api.dependencies.auth import get_caller, require_service
from adam_api.routers.admin import router as admin_router
from adam_api.routers.annuaire import router as annuaire_router
from adam_api.routers.benchmark import router as benchmark_router
from adam_api.routers.datasets import router as datasets_router
from adam_api.routers.document_fields import router as document_fields_router
from adam_api.routers.documents import router as documents_router
from adam_api.routers.files import router as files_router
from adam_api.routers.jobs import router as jobs_router
from adam_api.routers.ocr import router as ocr_router, status_router as ocr_status_router
from adam_api.routers.organisations import router as orgs_router
from adam_api.routers.projects import router as projects_router
from adam_api.routers.schemas import router as schemas_router
from adam_api.routers.users import me_router, router as users_router
from adam_core.db.session import ensure_database, get_engine, init_engine
from adam_core.utils.exceptions import http_exception_handler, response_validation_handler
from adam_core.utils.logging import get_logger, setup_logging

setup_logging(settings)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(
    fastapi_app: FastAPI,
) -> AsyncGenerator[None, None]:
    init_engine(settings.async_database_url, echo=False, **settings.engine_options)
    await ensure_database()
    logger.info("%s prete [port=%s]", fastapi_app.title, settings.api_port)
    yield
    await get_engine().dispose()


app = FastAPI(
    title=settings.api_title,
    version=settings.app_version,
    lifespan=lifespan,
)


install_jwt_middleware(app)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Content-Disposition : nom du PDF telecharge ; X-Total-Count : pagination.
    expose_headers=["X-Image-Dpi", "Content-Disposition", "X-Total-Count"],
)
# Le plus externe : compresse les reponses de plus de 1 Ko (les metriques d'un CERFA : ~10x plus legeres).
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(ResponseValidationError, response_validation_handler)

# Routers
PREFIX = "/api/" + settings.api_version

# Routes partagees
app.include_router(admin_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(orgs_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
# /users/me avant /users/{user_id}, qui capterait « me » ; et sans get_caller :
# la route resout elle-meme son caller, en creant l'agent a sa premiere connexion.
app.include_router(me_router, prefix=PREFIX)
app.include_router(users_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(annuaire_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(projects_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(schemas_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(datasets_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(documents_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(document_fields_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
app.include_router(benchmark_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
# /ocr-results/status avant les routes service de /ocr-results (/{ocr_result_id})
app.include_router(ocr_status_router, prefix=PREFIX, dependencies=[Depends(get_caller)])
# Routes service
app.include_router(files_router, prefix=PREFIX, dependencies=[Depends(require_service)])
app.include_router(ocr_router, prefix=PREFIX)

# Routes IHM
app.include_router(jobs_router, prefix=PREFIX, dependencies=[Depends(get_caller)])


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


#: Delai maximal accorde a la base pour repondre a la sonde de disponibilite.
_READINESS_TIMEOUT_SECONDS = 2.0


@app.get("/health", tags=["Monitoring"])
async def health() -> Dict[str, str]:
    """Sonde de vivacite : le processus repond.

    Ne touche aucune dependance. Une panne de la base ne doit pas faire redemarrer
    l'API, et ne le ferait qu'inutilement. Le corps reste minimal : la route est
    publique, ni version, ni environnement, ni port.
    """
    return {"status": "ok"}


@app.get("/health/ready", tags=["Monitoring"], response_model=None)
async def health_ready() -> JSONResponse:
    """Sonde de disponibilite : 200 si la base repond, 503 sinon.

    Sert a retirer l'instance du trafic sans la tuer. Le motif de l'echec est
    journalise, jamais renvoye : la route est publique et un message de driver
    peut citer l'hote ou la base.
    """
    try:
        async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("sonde de disponibilite : base injoignable", exc_info=True)
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "checks": {"database": "error"}}
        )
    return JSONResponse(content={"status": "ok", "checks": {"database": "ok"}})


@app.get("/", include_in_schema=False)
async def root() -> Dict[str, Any]:
    return {"message": f"NOTA API v{settings.app_version}"}
