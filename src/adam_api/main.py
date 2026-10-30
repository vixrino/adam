"""
API NOTA

Demarrage :
    python -m uvicorn adam_api.main:app --reload
"""

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
# from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
# from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.core.config import settings
from adam_api.core.security import install_jwt_middleware
from adam_api.dependencies.auth import get_caller, require_service, require_user
from adam_api.routers.admin import router as admin_router
from adam_api.routers.annuaire import router as annuaire_router
from adam_api.routers.datasets import router as datasets_router
from adam_api.routers.document_fields import router as document_fields_router
from adam_api.routers.documents import router as documents_router
from adam_api.routers.files import router as files_router
from adam_api.routers.jobs import router as jobs_router
from adam_api.routers.ocr import router as ocr_router
from adam_api.routers.organisations import router as orgs_router
from adam_api.routers.projects import router as projects_router
from adam_api.routers.schemas import router as schemas_router
from adam_api.routers.users import me_router, router as users_router
from adam_core.db.session import create_tables, ensure_database, get_engine, init_engine
from adam_core.models import Dataset, DocSchema, Document, File, Job, Organisation, Project, User
from adam_core.utils.exceptions import http_exception_handler
from adam_core.utils.logging import get_logger, setup_logging
from adam_core.utils.volumetry import estimate_table_size, format_size

setup_logging(settings)
logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "adam_core" / "static"


@asynccontextmanager
async def lifespan(
    fastapi_app: FastAPI,
) -> AsyncGenerator[None, None]:
    init_engine(settings.async_database_url, echo=False)
    await ensure_database()
    await create_tables()
    logger.info("%s prete [port=%s]", fastapi_app.title, settings.api_port)
    yield
    await get_engine().dispose()


app = FastAPI(
    title=settings.api_title,
    version=settings.app_version,
    lifespan=lifespan,
    # docs_url=None,
    # redoc_url=None,
)


install_jwt_middleware(app)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Image-Dpi"],
)

app.add_exception_handler(HTTPException, http_exception_handler)

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
# Routes service
app.include_router(files_router, prefix=PREFIX, dependencies=[Depends(require_service)])
app.include_router(ocr_router, prefix=PREFIX, dependencies=[Depends(require_service)])

# Routes IHM
app.include_router(jobs_router, prefix=PREFIX, dependencies=[Depends(get_caller)])

# Docs
# if STATIC_DIR.is_dir():
#     app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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


# @app.get("/docs", include_in_schema=False)
# async def docs() -> HTMLResponse:
#     return get_swagger_ui_html(
#         openapi_url="/openapi.json",
#         title=settings.api_title,
#         swagger_js_url="/static/swagger-ui-bundle.js",
#         swagger_css_url="/static/swagger-ui.css",
#         swagger_favicon_url="/static/favicon.ico",
#     )


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


# @app.get("/db-check", tags=["Monitoring"])
# async def db_check() -> Dict[str, Any]:
#     try:
#         async with get_engine().connect() as conn:
#             version = await conn.scalar(text("SELECT version()"))
#             db_name = await conn.scalar(text("SELECT current_database()"))
#             db_user = await conn.scalar(text("SELECT current_user"))
#             db_size = await conn.scalar(
#                 text("SELECT pg_size_pretty(pg_database_size(current_database()))")
#             )
#             table_count = await conn.scalar(
#                 text(
#                     "SELECT COUNT(*) FROM information_schema.tables "
#                     "WHERE table_schema = 'public'"
#                 )
#             )
#         return {
#             "status": "ok",
#             "database": {
#                 "version": version,
#                 "name": db_name,
#                 "user": db_user,
#                 "size": db_size,
#                 "table_count": table_count,
#             },
#         }
#     except Exception as exc:  # pylint: disable=broad-exception-caught
#         return {"status": "error", "detail": str(exc)}


# @app.get("/debug-env", tags=["Monitoring"])
# async def debug_env() -> Dict[str, Any]:
#     return {
#         "runtime": {
#             "cwd": os.getcwd(),
#             "python_path": os.getenv("PYTHONPATH", "non defini"),
#         },
#         "app": {
#             "name": settings.app_name,
#             "version": settings.app_version,
#             "env": settings.app_env,
#             "is_dev": settings.is_dev,
#         },
#         "database": {
#             "host": settings.postgres_host,
#             "port": settings.postgres_port,
#             "db": settings.postgres_db,
#             "user": settings.postgres_user,
#             "password_set": bool(settings.postgres_password),
#         },
#         "api": {
#             "host": settings.api_host,
#             "port": settings.api_port,
#             "cors_origins": settings.cors_origins,
#         },
#         "ocr": {
#             "mock_enabled": settings.ocr_mock_enabled,
#         },
#     }


# @app.get("/volumetry", tags=["Monitoring"])
# async def volumetry() -> Dict[str, Any]:
#     """Estime la volumetrie de chaque table en BDD."""
#     _tables: List[Any] = [
#         Organisation,
#         User,
#         Project,
#         DocSchema,
#         Dataset,
#         File,
#         Document,
#         Job,
#     ]
#     _names = [
#         "organisation",
#         "user",
#         "project",
#         "doc_schema",
#         "dataset",
#         "file",
#         "document",
#         "job",
#     ]

#     result: Dict[str, Any] = {}
#     async with get_engine().connect() as conn:
#         session = AsyncSession(bind=conn)
#         for name, model in zip(_names, _tables):
#             rows = list((await session.execute(select(model))).scalars().all())
#             result[name] = estimate_table_size(rows)

#     total = sum(t["total_bytes"] for t in result.values())
#     return {"tables": result, "grand_total": format_size(total)}


@app.get("/", include_in_schema=False)
async def root() -> Dict[str, Any]:
    return {"message": f"NOTA API v{settings.app_version}"}