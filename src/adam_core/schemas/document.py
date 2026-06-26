"""Pydantic schemas for Document API responses."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    file_id: int
    file_name: str
    status: str
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata_")
