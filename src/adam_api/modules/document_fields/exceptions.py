"""Erreurs metier du module document_fields.

Elles sont levees par le service et traduites en codes HTTP par le routeur. Le
service ne connait donc pas FastAPI, et reste appelable depuis un contexte qui
n'est pas une requete — une commande d'administration, un test.
"""

from __future__ import annotations

from typing import Optional, Sequence


class DocumentFieldError(Exception):
    """Racine des erreurs du module, pour un `except` unique cote appelant."""


class FieldSpecMismatch(DocumentFieldError):
    """Un field_spec_id n'appartient pas au schema du document.

    Traduite en 422 : la demande est syntaxiquement valide mais incoherente, ce
    n'est ni une ressource absente ni un conflit.
    """

    def __init__(self, field_spec_ids: Sequence[int], schema_id: int) -> None:
        self.field_spec_ids = list(field_spec_ids)
        self.schema_id = schema_id
        super().__init__(
            f"field_spec_id {self.field_spec_ids} n'appartiennent pas au schema {schema_id}"
        )


class DuplicateField(DocumentFieldError):
    """Le triplet (document_id, field_spec_id, group_id) existe deja.

    Traduite en 409 sur la creation unitaire. La creation en lot ne la leve
    jamais : elle rapporte les doublons au lieu d'echouer, pour rester
    rejouable.
    """

    def __init__(self, field_spec_id: int, group_id: Optional[str]) -> None:
        self.field_spec_id = field_spec_id
        self.group_id = group_id
        super().__init__(
            f"Le champ field_spec_id={field_spec_id} group_id={group_id!r} existe deja "
            f"pour ce document"
        )
