"""Service de rendu des images de page, partage entre /documents et /schemas.

Meme logique de resolution (bornes du page_count, presence sur le PVC) pour
les deux appelants : seule la maniere dont ils obtiennent le FILE differe
(Document.file vs DocSchema.specimen_file).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Type

from anyio import Path as AsyncPath
from fastapi.responses import FileResponse

from adam_api.core.config import settings
from adam_core.models import File
from adam_core.utils.exceptions import raise_not_found
from adam_core.utils.pdf_render import PAGE_IMAGE_DPI, page_image_relative_path


async def serve_page_image(
    model: Type[Any],
    file: Optional[File],
    page_number: int,
    *,
    no_file_detail: str,
) -> FileResponse:
    if file is None:
        raise_not_found(model, no_file_detail)

    if page_number < 1 or page_number > file.page_count:
        raise_not_found(
            model,
            f"Page {page_number} hors bornes (document de {file.page_count} page(s))",
        )

    image_path = Path(settings.pvc_mount_path) / page_image_relative_path(file.id, page_number)
    async_image_path = AsyncPath(image_path)
    if not await async_image_path.is_file():
        raise_not_found(
            model,
            f"Image de la page {page_number} absente du PVC (images non generees)",
        )

    return FileResponse(
        image_path,
        media_type="image/png",
        filename=image_path.name,
        headers={"X-Image-Dpi": str(PAGE_IMAGE_DPI)},
    )
