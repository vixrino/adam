"""Application FastAPI ADAM."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from adam_api.core.config import settings
from adam_api.routers import (
    admin,
    datasets,
    documents,
    files,
    jobs,
    ocr,
    organisations,
    projects,
    schemas,
    users,
)
from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.exceptions import http_exception_handler
from adam_core.utils.logging import setup_logging

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)
    yield


app = FastAPI(title=settings.api_title, version=settings.app_version, lifespan=lifespan)
app.add_exception_handler(Exception, http_exception_handler)

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

app.include_router(admin.router)
app.include_router(datasets.router)
app.include_router(documents.router)
app.include_router(files.router)
app.include_router(jobs.router)
app.include_router(ocr.router)
app.include_router(organisations.router)
app.include_router(projects.router)
app.include_router(schemas.router)
app.include_router(users.router)


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
