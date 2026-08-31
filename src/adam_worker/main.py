"""Point d'entree des workers ADAM : lance tous les workers en parallele.

Stub minimal Sprint 3 : pas de scheduler, chaque worker boucle sur son
propre polling (voir BaseWorker.run_forever).
"""

from __future__ import annotations

import asyncio
import signal

from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.logging import setup_logging
from adam_worker.base_worker import BaseWorker
from adam_worker.consensus_worker import ConsensusWorker
from adam_worker.page_image_worker import PageImageWorker


def _install_signal_handlers(workers: list[BaseWorker]) -> None:
    """Graceful shutdown : sur SIGINT/SIGTERM (k8s), demande l'arret de chaque
    worker, qui terminera son cycle en cours avant de s'arreter.

    add_signal_handler n'est pas supporte sur Windows : on l'ignore alors
    (contexte dev uniquement, le deploiement reel tourne sous Linux).
    """
    def _request_stop() -> None:
        for worker in workers:
            worker.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)

    workers: list[BaseWorker] = [PageImageWorker(), ConsensusWorker()]
    _install_signal_handlers(workers)
    await asyncio.gather(*(worker.run_forever() for worker in workers))


if __name__ == "__main__":
    asyncio.run(_main())
