from __future__ import annotations

import asyncio
import signal

from adam_core.core.config import get_core_settings
from adam_core.db.session import ensure_database, init_engine
from adam_core.utils.logging import setup_logging
from adam_worker.base_worker import BaseWorker
from adam_worker.benchmark.worker import TestExecutionWorker
from adam_worker.consensus_worker import ConsensusWorker
from adam_worker.page_image_worker import PageImageWorker
from adam_worker.prepopulation.poller import PrepopulationWorker


def _install_signal_handlers(workers: list[BaseWorker]) -> None:
    def _request_stop() -> None:
        for worker in workers:
            worker.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass


async def main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=False)
    await ensure_database()

    workers: list[BaseWorker] = [
        PageImageWorker(),
        ConsensusWorker(),
        PrepopulationWorker(),
        TestExecutionWorker(),
    ]
    _install_signal_handlers(workers)
    await asyncio.gather(*(worker.run_forever() for worker in workers))


if __name__ == "__main__":
    asyncio.run(main())
