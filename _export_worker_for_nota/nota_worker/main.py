"""Point d'entree des workers : lance tous les workers en parallele."""

from __future__ import annotations

import asyncio

from nota_core.core.config import get_core_settings
from nota_core.db.session import init_engine
from nota_core.utils.logging import setup_logging
from nota_worker.page_image_worker import PageImageWorker


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)

    workers = [PageImageWorker()]
    await asyncio.gather(*(worker.run_forever() for worker in workers))


if __name__ == "__main__":
    asyncio.run(_main())
