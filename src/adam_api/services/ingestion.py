"""Service d'ingestion de fichiers PDF bruts vers le PVC.

Flux amont (Sprint 3) : depose des PDF sur le PVC et cree les
enregistrements FILE et DOCUMENT, sans donnees OCR. Ce flux rend les
documents disponibles pour le mini worker de generation d'images puis,
plus tard, pour le flux OCR.

Deduplication : scopee au dataset. L'enregistrement FILE est partage par
hash SHA-256 (unique global), mais un meme contenu peut etre rattache a
des Documents distincts dans des datasets differents. Le chemin physique
d'un FILE est fixe a sa premiere creation (organisation/type/horodatage
de ce premier upload) ; une ingestion ulterieure du meme contenu par une
autre organisation reutilise ce chemin, elle n'en cree pas un nouveau.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple, cast

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
        # pymupdf expose py.typed mais Document.__init__ n'a pas d'annotations :
        # l'appel et l'attribut suivant sont donc non types cote lib, pas cote nous.
        doc = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
    except RuntimeError:
        return False
    try:
        return cast(int, doc.page_count) > 0
    finally:
        doc.close()  # type: ignore[no-untyped-call]


def pvc_relative_path(
    *, organisation_slug: str, document_type: str, ingested_at: datetime, file_name: str
) -> Path:
    """Chemin lisible : organisation/type_document/horodatage/nom_fichier.

    Le nom de fichier envoye par le client n'est jamais renomme, seulement
    ramene a son basename (`Path(file_name).name`) pour empecher toute
    traversee de repertoire : c'est une entree utilisateur falsifiable
    (cf. looks_like_pdf).
    """
    timestamp = ingested_at.strftime("%Y_%m_%d_%H%M")
    safe_name = Path(file_name).name
    return Path(organisation_slug) / document_type / timestamp / safe_name


async def _get_or_create_file(
    db: AsyncSession, *, checksum: str, content: bytes, pvc_root: Path, relative_path: Path
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

    if file_row is not None:
        abs_path = pvc_root / file_row.file_path
        if not abs_path.exists():  # robustesse : re-materialise le contenu si manquant
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(content)
        return file_row, False

    abs_path = pvc_root / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)

    stmt = (
        pg_insert(File)
        .values(
            file_path=relative_path.as_posix(),
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
    organisation_slug: str,
    document_type: str,
    file_name: str,
    content: bytes,
    pvc_root: Path,
) -> dict[str, Any]:
    """Ingere un PDF dans un dataset. Idempotent au sein du dataset."""
    checksum = sha256_bytes(content)

    existing = (
        await db.execute(
            select(Document, File.file_path)
            .join(File, Document.file_id == File.id)
            .where(Document.dataset_id == dataset.id)
            .where(File.sha256_checksum == checksum)
        )
    ).one_or_none()
    if existing is not None:
        existing_doc, existing_file_path = existing
        logger.info(
            "Fichier deja present dans le dataset [dataset_id=%s document_id=%s sha256=%s...]",
            dataset.id,
            existing_doc.id,
            checksum[:12],
        )
        return {
            "file_name": file_name,
            "status": "already_exists",
            "document_id": existing_doc.id,
            "file_id": existing_doc.file_id,
            "file_path": existing_file_path,
        }

    relative_path = pvc_relative_path(
        organisation_slug=organisation_slug,
        document_type=document_type,
        ingested_at=datetime.now(timezone.utc),
        file_name=file_name,
    )
    file_row, file_created = await _get_or_create_file(
        db, checksum=checksum, content=content, pvc_root=pvc_root, relative_path=relative_path
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
        "status": "created" if file_created else "created_file_reused",
        "document_id": document.id,
        "file_id": file_row.id,
        "file_path": file_row.file_path,
    }
