"""SNIPPET a greffer dans le documents.py de nota — ne pas copier le fichier entier.

1. Ajouter les imports ci-dessous a ceux deja presents dans documents.py.
2. Coller la fonction get_document_page_image dans le router existant
   (par exemple juste apres get_document).

Le reste du documents.py d'adam contient du code d'autres tickets
(value_type / field parser, schemas divergents) qui ne compile pas sur nota.
"""

# --- imports a ajouter -------------------------------------------------------

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException  # HTTPException en plus
from fastapi.responses import FileResponse

from nota_api.core.config import settings
from nota_core.utils.pdf_render import page_image_relative_path

# --- endpoint a greffer ------------------------------------------------------
# (suppose les memes `router`, `get_db`, `Document`, `raise_not_found`,
#  `select` et `selectinload` que le reste du fichier)


@router.get("/{document_id}/pages/{page_number}")
async def get_document_page_image(
    document_id: int,
    page_number: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Retourne l'image PNG d'une page du document, lue depuis le PVC (file_id/pages/).

    404 si le document n'existe pas, si la page est hors bornes du page_count,
    ou si les images n'ont pas encore ete generees par le worker.
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id).options(selectinload(Document.file))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise_not_found(Document)
    if doc.file is None:
        raise HTTPException(status_code=404, detail="Aucun fichier associe a ce document")

    # CA-4 : page 1-indexee, bornee par le page_count renseigne par le worker
    if page_number < 1 or page_number > doc.file.page_count:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page_number} hors bornes (document de {doc.file.page_count} page(s))",
        )

    image_path = Path(settings.pvc_mount_path) / page_image_relative_path(doc.file.id, page_number)
    if not image_path.is_file():
        # CA-3 : le worker n'a pas (encore) genere les images de ce document
        raise HTTPException(
            status_code=404,
            detail=f"Image de la page {page_number} absente du PVC (images non generees)",
        )
    return FileResponse(image_path, media_type="image/png", filename=image_path.name)
