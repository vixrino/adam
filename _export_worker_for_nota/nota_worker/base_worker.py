"""Worker de polling generique, herite par chaque worker concret.

Stub minimal Sprint 3 : une boucle avec delai fixe, pas de scheduler.
Une erreur dans un cycle de `poll()` est loguee sans interrompre la
boucle, pour qu'un worker ne meure jamais sur un incident isole.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from nota_core.utils.logging import get_logger


class BaseWorker(ABC):
    """Boucle de polling : sous-classer et implementer `poll()`."""

    poll_interval_seconds: float = 5.0

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__module__)

    @abstractmethod
    async def poll(self) -> None:
        """Execute un cycle de polling complet (une passe sur le travail en attente)."""

    async def run_forever(self) -> None:
        self.logger.info(
            "%s demarre (poll_interval=%ss)", self.__class__.__name__, self.poll_interval_seconds
        )
        while True:
            try:
                await self.poll()
            except Exception:
                self.logger.exception("%s: echec du cycle de polling", self.__class__.__name__)
            await asyncio.sleep(self.poll_interval_seconds)
