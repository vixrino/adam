"""Point d'entree du seul DocumentProgressWorker.

Complement de main.py, qui lance l'ensemble des workers. Sur une branche ou
PageImageWorker et ConsensusWorker ne sont pas encore presents, importer main.py
entraine toute leur chaine de dependances — rendu PDF, service de consensus —
pour un worker qui n'en utilise aucune. Ce point d'entree n'importe que ce dont
il a besoin.

Utile aussi pour faire tourner ce worker seul, dans un pod dedie ou pendant une
mise au point, sans reveiller les autres.

    python -m adam_worker.progress_main

echo est force a False : avec APP_ENV=dev, l'echo SQLAlchemy imprime chaque
requete et noie la seule ligne qui compte, celle du cycle.
"""

from __future__ import annotations

import asyncio

from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.logging import setup_logging
from adam_worker.document_progress_worker import DocumentProgressWorker


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=False)

    await DocumentProgressWorker().run_forever()


if __name__ == "__main__":
    # Ctrl+C interrompt l'asyncio.sleep de la boucle et remonte jusqu'ici. On
    # l'absorbe pour sortir sans trace : un arret demande n'est pas une erreur.
    # Pas d'appel a stop() ni de gestionnaire de signal, qui supposeraient une
    # version precise de BaseWorker ; l'arret ordonne est le role de main.py.
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
