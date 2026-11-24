"""Worker de polling generique, herite par chaque worker concret.

Stub minimal Sprint 3 : une boucle avec delai fixe, pas de scheduler.
Une erreur dans un cycle de `poll()` est loguee sans interrompre la
boucle, pour qu'un worker ne meure jamais sur un incident isole.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import math

from adam_core.db import settings_store
from adam_core.utils.logging import get_logger

#: Plancher du delai lu en base : une valeur a 0 ferait tourner le worker a vide.
MIN_POLL_INTERVAL_SECONDS = 1.0


class BaseWorker(ABC):
    """Boucle de polling : sous-classer et implementer `poll()`.

    Le delai entre deux cycles se regle en base, cle `worker.<NomDeClasse>.poll_interval`
    (secondes) ; `poll_interval_seconds` sert de defaut quand la cle manque.
    """

    poll_interval_seconds: float = 5.0

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__module__)
        self._is_running = True

    @abstractmethod
    async def poll(self) -> None:
        """Execute un cycle de polling complet (une passe sur le travail en attente)."""

    async def run_forever(self) -> None:
        self.logger.info(
            "%s demarre (poll_interval=%ss)", self.__class__.__name__, self.poll_interval_seconds
        )
        while self._is_running:
            try:
                await self.poll()
            except Exception:
                self.logger.exception("%s: echec du cycle de polling", self.__class__.__name__)
            if self._is_running:
                await asyncio.sleep(await self._current_interval())
        self.logger.info("%s arrete proprement", self.__class__.__name__)

    async def _current_interval(self) -> float:
        """Delai de ce cycle : la base si la cle est valable, sinon le defaut de la classe."""
        key = f"worker.{self.__class__.__name__}.poll_interval"
        try:
            value = (await settings_store.load()).get(key)
        except Exception as exc:
            self.logger.warning("lecture de %s impossible (%s), delai par defaut", key, exc)
            return self.poll_interval_seconds
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            if value is not None:
                self.logger.warning("%s invalide (%r), delai par defaut", key, value)
            return self.poll_interval_seconds
        return max(float(value), MIN_POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        """Demande l'arret du worker a la fin de son cycle actuel (graceful shutdown)."""
        self.logger.info(
            "Signal d'arret recu, %s s'arretera apres le traitement en cours...",
            self.__class__.__name__,
        )
        self._is_running = False
