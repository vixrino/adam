"""Erreurs metier des document_fields."""

from __future__ import annotations

from typing import Optional, Sequence


class DocumentFieldError(Exception):
    """Racine des erreurs du module, pour un `except` unique cote appelant."""


class FieldSpecMismatch(DocumentFieldError):
    """Un field_spec_id n'appartient pas au schema du document."""

    def __init__(self, field_spec_ids: Sequence[int], schema_id: int) -> None:
        self.field_spec_ids = list(field_spec_ids)
        self.schema_id = schema_id
        super().__init__(
            f"field_spec_id {self.field_spec_ids} n'appartiennent pas au schema {schema_id}"
        )


class DuplicateField(DocumentFieldError):
    """Le triplet (document_id, field_spec_id, group_id) existe deja."""

    def __init__(self, field_spec_id: int, group_id: Optional[str]) -> None:
        self.field_spec_id = field_spec_id
        self.group_id = group_id
        super().__init__(
            f"Le champ field_spec_id={field_spec_id} group_id={group_id!r} existe deja "
            f"pour ce document"
        )
