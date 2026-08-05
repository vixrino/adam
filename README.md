# ADAM - Annotation et Données Automatisées

Oui, et c'est même la meilleure option dans ta situation. Un point d'entrée dédié n'a aucun fichier en commun avec develop, donc zéro conflit au merge — c'est plus propre que de bricoler main.py.

1. Rends main.py à develop et arrête d'y toucher :

git checkout HEAD -- src/nota_worker/main.py

Si ta branche n'en avait pas du tout, supprime simplement le fichier — tu le récupéreras intact au merge.

2. Garde base_worker.py, il est indispensable et n'importe que nota_core.utils.logging. C'est la seule dépendance de la chaîne.

3. Crée src/nota_worker/progress_main.py :

"""Point d'entree du seul DocumentProgressWorker.

Separe de main.py, qui lance l'ensemble des workers : tant que
PageImageWorker et ConsensusWorker ne sont pas sur cette branche, importer
main.py entraine toute leur chaine de dependances (pdf_render, services de
consensus) pour un worker qui n'en a besoin d'aucune.

A supprimer au merge de develop, au profit d'une ligne dans main.py.
"""

from __future__ import annotations

import asyncio

from nota_core.core.config import get_core_settings
from nota_core.db.session import init_engine
from nota_core.utils.logging import setup_logging
from nota_worker.document_progress_worker import DocumentProgressWorker


async def _main() -> None:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=core.is_dev)
    await DocumentProgressWorker().run_forever()


if __name__ == "__main__":
    asyncio.run(_main())

4. Lance :

uv run python -m nota_worker.progre

Et tu peux supprimer page_image_woruter, il ne te sert plus à rien.
                                                                                                   Le test test_le_worker_est_enregistnt sauté, puisqu'il passe parimportorskip — c'est exactement le cas qu'il prévoyait. Si tu préfères qu'il vérifie quelque chose en attendant, remplace "nota_workerogress_main" et l'assertion parassert "DocumentProgressWorker" in inspect.getsource(main._main).                            
Au merge de develop, tu supprimes progress_main.py et tu ajoutes ta ligne dans main.py. Deux minutes, sans conflit.
