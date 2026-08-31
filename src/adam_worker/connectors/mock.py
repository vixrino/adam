"""Connecteur OCR de substitution, en attendant le moteur reel.

Il ne lit pas les images : il fabrique une reponse conforme au contrat v0.3 a
partir des cles qu'on lui donne. Cela suffit a exercer toute la chaine de
pre-alimentation — fusion, creation des champs, transition de statut — sans
dependre d'un moteur externe.

Trois comportements, parce que ce sont les trois cas que le merger doit traiter
et qu'un mock qui ne saurait que reussir ne prouverait rien :

    detected_keys renseignees   les cles listees portent une valeur
    detected_keys vide          document rendu, aucun champ detecte
    available=False             extract rend None, OCR indisponible

`failing` est distinct de `available` : il leve OcrConnectorError au lieu de
rendre None, pour couvrir l'echec technique que la chaine doit traiter en ERROR
alors qu'une absence de resultat est un cas nominal.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from adam_core.schemas.interface_contract import (
    KVPair,
    KVTextValue,
    Page,
    Section,
    SmartdocDocument,
)
from adam_worker.connectors.base import BaseOcrConnector, OcrConnectorError

#: Polygone arbitraire, pour que les champs detectes en portent un.
_DEFAULT_POLYGON = [10.0, 10.0, 200.0, 10.0, 200.0, 40.0, 10.0, 40.0]


class MockOcrConnector(BaseOcrConnector):
    """Connecteur deterministe, pilote par sa configuration."""

    name = "mock"

    def __init__(
        self,
        detected_keys: Optional[Sequence[str]] = None,
        *,
        value: str = "valeur-mock",
        confidence: float = 0.95,
        available: bool = True,
        failing: bool = False,
    ) -> None:
        self.detected_keys = list(detected_keys or [])
        self.value = value
        self.confidence = confidence
        self.available = available
        self.failing = failing

    async def extract(self, images: Sequence[Path]) -> Optional[SmartdocDocument]:
        if self.failing:
            raise OcrConnectorError("connecteur mock configure en echec")
        if not self.available:
            return None
        return self._build_document(page_count=max(len(images), 1))

    def _build_document(self, page_count: int) -> SmartdocDocument:
        """Groupe les cles detectees par section, telles que le contrat l'attend."""
        sections: dict[str, List[KVPair]] = {}
        for key in self.detected_keys:
            section_id = key.split(".", 1)[0]
            sections.setdefault(section_id, []).append(
                KVPair(
                    id=key,
                    value=KVTextValue(
                        text=self.value,
                        polygon=list(_DEFAULT_POLYGON),
                        confidence=self.confidence,
                    ),
                )
            )

        return SmartdocDocument(
            smartdoc_version="0.3",
            document_id="mock",
            page_count=page_count,
            pages=[
                Page(
                    page_number=1,
                    width=1240,
                    height=1754,
                    sections=[
                        Section(id=section_id, label=section_id.capitalize(), kv_pairs=pairs)
                        for section_id, pairs in sections.items()
                    ],
                )
            ],
            metadata={"provider": "mock"},
        )
