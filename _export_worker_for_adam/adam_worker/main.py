"""Point d'entree des workers : lance tous les workers en parallele.

Stub minimal Sprint 3 : pas de scheduler, chaque worker boucle sur son
propre polling (voir BaseWorker.run_forever).

NOTE PORTAGE ADAM : ne pas ecraser le main.py existant de adam avec ce
fichier. Ajouter seulement PageImageWorker() a la liste `workers` du
main.py de adam, en conservant les workers deja enregistres la-bas
(le ConsensusWorker d'adam n'existe pas sous ce nom sur adam).
"""

from __future__ import annotations

import asyncio

from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.logging import setup_logging
from adam_worker.page_image_worker import PageImageWorker


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)

    workers = [PageImageWorker()]
    await asyncio.gather(*(worker.run_forever() for worker in workers))


if __name__ == "__main__":
    asyncio.run(_main())
