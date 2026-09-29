"""Point d'entree unique des deploiements ADAM : l'API ou les workers.

    python launcher.py api
    python launcher.py worker

Chaque mode n'importe que ce dont il a besoin : le pod API ne charge pas la
chaine des workers (rendu PDF, consensus), le pod worker ne charge pas
l'application FastAPI. D'ou les imports places dans les fonctions.

Contrairement a scripts/run_dev.py, l'API tourne ici sans rechargement a chaud
et ecoute sur API_HOST : c'est le lanceur des pods, pas celui du poste de dev.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Sequence


def _run_api() -> None:
    # pylint: disable=import-outside-toplevel
    import uvicorn

    from adam_api.core.config import settings

    # log_config=None laisse la main a setup_logging, appele dans le lifespan :
    # sans cela, uvicorn installe ses propres handlers et chaque ligne sort
    # dans deux formats.
    uvicorn.run(
        "adam_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
        access_log=False,
    )


def _run_worker() -> None:
    # pylint: disable=import-outside-toplevel
    from adam_worker.main import main as run_workers

    # Sous Linux, main() installe les gestionnaires SIGINT/SIGTERM et l'arret
    # est ordonne. Sous Windows, add_signal_handler n'existe pas : Ctrl+C
    # remonte en KeyboardInterrupt, qu'on absorbe, un arret demande n'etant
    # pas une erreur.
    try:
        asyncio.run(run_workers())
    except KeyboardInterrupt:
        pass


_TARGETS = {"api": _run_api, "worker": _run_worker}


def main(argv: Sequence[str] | None = None) -> int:
    """Lance la cible demandee et rend le code de sortie du processus."""
    parser = argparse.ArgumentParser(description="Lanceur ADAM : API ou workers.")
    parser.add_argument("target", choices=sorted(_TARGETS), help="composant a lancer")
    args = parser.parse_args(argv)

    _TARGETS[args.target]()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
