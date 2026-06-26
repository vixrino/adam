from typing import Any

from fastapi import APIRouter, HTTPException

from adam_api.core.config import settings
from adam_api.services.consensus import try_resolve

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/admin/consensus/resolve/{document_id}", include_in_schema=True)
async def force_resolve(document_id: int, dataset_id: int) -> dict[str, Any]:
    if not settings.is_dev:
        raise HTTPException(status_code=403)
    result = await try_resolve(document_id, dataset_id)
    return result
