"""Point d'entree du seul PrepopulationWorker.

Complement de main.py, qui lance l'ensemble des workers. Sur une branche ou
PageImageWorker et ConsensusWorker ne sont pas encore presents, importer main.py
entraine toute leur chaine de dependances — rendu PDF, service de consensus —
pour un worker qui n'en utilise aucune. Ce point d'entree n'importe que ce dont
il a besoin.

Utile aussi pour faire tourner ce worker seul, dans un pod dedie ou pendant une
mise au point, sans reveiller les autres.

    python -m adam_worker.prepopulation_main

Attention : ce worker ecrit les champs par HTTP, il lui faut donc une API
joignable. Pour verifier son comportement sans lancer de serveur, preferer
scripts/test_prepopulation_worker.py, qui parle a l'application en memoire.

echo est force a False : avec APP_ENV=dev, l'echo SQLAlchemy imprime chaque
requete et noie les lignes du cycle.
"""

from __future__ import annotations

import asyncio

from adam_core.core.config import get_core_settings
from adam_core.db.session import init_engine
from adam_core.utils.logging import setup_logging
from adam_worker.prepopulation.poller import PrepopulationWorker


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=False)

    await PrepopulationWorker().run_forever()


if __name__ == "__main__":
    # Ctrl+C interrompt l'asyncio.sleep de la boucle et remonte jusqu'ici. On
    # l'absorbe pour sortir sans trace : un arret demande n'est pas une erreur.
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
