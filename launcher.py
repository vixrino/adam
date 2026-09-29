"""Point d'entree unique des deploiements ADAM : l'API, les workers, ou les deux.

    python launcher.py api
    python launcher.py worker
    python launcher.py all

Chaque mode n'importe que ce dont il a besoin : le pod API ne charge pas la
chaine des workers (rendu PDF, consensus), le pod worker ne charge pas
l'application FastAPI. D'ou les imports places dans les fonctions.

Contrairement a scripts/run_dev.py, l'API tourne ici sans rechargement a chaud
et ecoute sur API_HOST : c'est le lanceur des pods, pas celui du poste de dev.

`all` lance l'API et les workers dans deux processus fils, pas dans un seul :
chacun garde ainsi sa propre gestion des signaux, et un worker qui plante ne
fait pas tomber l'API avec lui. Pratique en dev ; en production, un pod par
composant reste la regle.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

#: Delai laisse a un processus fils pour finir son cycle avant d'etre tue.
_STOP_TIMEOUT_SECONDS = 30


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


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Attend la fin d'un processus fils, et le tue s'il depasse le delai."""
    try:
        process.wait(timeout=_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _first_exit_code(processes: list[subprocess.Popen[bytes]]) -> int:
    """Premier code de sortie non nul parmi les fils arretes, 0 sinon."""
    return next((process.returncode for process in processes if process.returncode), 0)


def _run_all() -> int:
    script = str(Path(__file__).resolve())
    processes = [subprocess.Popen([sys.executable, script, target]) for target in ("api", "worker")]
    try:
        # Des qu'un des deux s'arrete, l'autre n'a plus de sens seul : l'API
        # sans workers laisse les documents en attente, les workers sans API
        # echouent a ecrire les champs.
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        # Releve avant d'arreter l'autre fils : son code d'arret force (-15)
        # masquerait celui du fils qui a lache le premier, le seul qui explique.
        exit_code = _first_exit_code(processes)
    except KeyboardInterrupt:
        # Ctrl+C atteint deja chaque fils, qui partage la console : on les
        # laisse s'arreter d'eux-memes plutot que de les couper en plein cycle.
        for process in processes:
            _stop(process)
        exit_code = _first_exit_code(processes)
    finally:
        for process in processes:
            if process.poll() is None:
                # L'autre fils s'est arrete : SIGTERM sous Linux, que l'API
                # comme les workers traitent proprement ; arret immediat
                # sous Windows.
                process.terminate()
        for process in processes:
            _stop(process)
    return exit_code


_TARGETS: dict[str, Callable[[], int | None]] = {
    "api": _run_api,
    "worker": _run_worker,
    "all": _run_all,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Lance la cible demandee et rend le code de sortie du processus."""
    parser = argparse.ArgumentParser(description="Lanceur ADAM : API, workers, ou les deux.")
    parser.add_argument("target", choices=sorted(_TARGETS), help="composant a lancer")
    args = parser.parse_args(argv)

    return _TARGETS[args.target]() or 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
