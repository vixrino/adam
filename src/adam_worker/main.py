"""Point d'entree des workers ADAM : lance tous les workers en parallele.

Stub minimal Sprint 3 : pas de scheduler, chaque worker boucle sur son
propre polling (voir BaseWorker.run_forever).
"""

from __future__ import annotations

import asyncio

from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.logging import setup_logging
from adam_worker.consensus_worker import ConsensusWorker
from adam_worker.page_image_worker import PageImageWorker


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)

    workers = [PageImageWorker(), ConsensusWorker()]
    await asyncio.gather(*(worker.run_forever() for worker in workers))


if __name__ == "__main__":
    asyncio.run(_main())
