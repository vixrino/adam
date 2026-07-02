"""Service d'ingestion de fichiers PDF bruts vers le PVC.

Flux amont (Sprint 3) : depose des PDF sur le PVC et cree les
enregistrements FILE et DOCUMENT, sans donnees OCR. Ce flux rend les
documents disponibles pour le mini worker de generation d'images puis,
plus tard, pour le flux OCR.

Deduplication : scopee au dataset. L'enregistrement FILE est partage par
hash SHA-256 (unique global), mais un meme contenu peut etre rattache a
des Documents distincts dans des datasets differents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

import pymupdf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from adam_core.enums.status import DocumentStatus
from adam_core.models import Dataset, Document, File
from adam_core.utils.hashing import sha256_bytes
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

PDF_MIME = "application/pdf"


def looks_like_pdf(content: bytes) -> bool:
    """Valide que le contenu est un PDF structurellement correct (via pymupdf).

    content-type et nom de fichier sont fournis par le client et donc
    falsifiables : ils ne sont jamais utilises comme critere de validation.
    """
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            return doc.page_count > 0
    except RuntimeError:
        return False


def pvc_relative_path(checksum: str) -> Path:
    """Chemin content-addressed, partage entre datasets (par hash)."""
    return Path("documents") / checksum[:2] / checksum[2:4] / f"{checksum}.pdf"


async def _get_or_create_file(
    db: AsyncSession, *, checksum: str, content: bytes, pvc_root: Path
) -> Tuple[File, bool]:
    """Reutilise le FILE existant (par hash) ou le cree, en ecrivant sur le PVC.

    L'INSERT utilise ON CONFLICT DO NOTHING sur sha256_checksum (contrainte
    unique) pour rester correct sous ingestion concurrente du meme contenu :
    si une autre transaction a cree la ligne entre notre SELECT et notre
    INSERT, on ne leve pas d'IntegrityError, on relit la ligne gagnante.
    """
    file_row = (
        await db.execute(select(File).where(File.sha256_checksum == checksum))
    ).scalar_one_or_none()

    abs_path = pvc_root / pvc_relative_path(checksum)
    if file_row is not None:
        if not abs_path.exists():  # robustesse : re-materialise le contenu si manquant
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(content)
        return file_row, False

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)

    stmt = (
        pg_insert(File)
        .values(
            file_path=str(pvc_relative_path(checksum)),
            storage_type="pvc",
            mime_type=PDF_MIME,
            file_size_bytes=len(content),
            sha256_checksum=checksum,
        )
        .on_conflict_do_nothing(index_elements=[File.sha256_checksum])
        .returning(File)
    )
    file_row = (await db.execute(stmt)).scalar_one_or_none()
    if file_row is not None:
        await db.flush()
        return file_row, True

    # Course perdue : une autre transaction a insere la ligne en premier.
    file_row = (
        await db.execute(select(File).where(File.sha256_checksum == checksum))
    ).scalar_one()
    return file_row, False


async def ingest_pdf(
    db: AsyncSession,
    dataset: Dataset,
    *,
    file_name: str,
    content: bytes,
    pvc_root: Path,
) -> dict[str, Any]:
    """Ingere un PDF dans un dataset. Idempotent au sein du dataset."""
    checksum = sha256_bytes(content)

    existing = (
        await db.execute(
            select(Document)
            .join(File, Document.file_id == File.id)
            .where(Document.dataset_id == dataset.id)
            .where(File.sha256_checksum == checksum)
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "Fichier deja present dans le dataset [dataset_id=%s document_id=%s sha256=%s...]",
            dataset.id,
            existing.id,
            checksum[:12],
        )
        return {
            "file_name": file_name,
            "status": "already_exists",
            "document_id": existing.id,
            "file_id": existing.file_id,
        }

    file_row, file_created = await _get_or_create_file(
        db, checksum=checksum, content=content, pvc_root=pvc_root
    )
    document = Document(
        dataset_id=dataset.id,
        file_id=file_row.id,
        file_name=file_name,
        status=DocumentStatus.RECEIVED.value,
    )
    db.add(document)
    await db.flush()
    logger.info(
        "Document ingere [dataset_id=%s document_id=%s file_id=%s file_created=%s]",
        dataset.id,
        document.id,
        file_row.id,
        file_created,
    )
    return {
        "file_name": file_name,
        "status": "created",
        "document_id": document.id,
        "file_id": file_row.id,
        "file_reused": not file_created,
    }
