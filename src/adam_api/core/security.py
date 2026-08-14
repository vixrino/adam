"""
Montage du middleware de validation du token JWT BdF.

La validation est deleguee au connecteur exa-pie, qui verifie la signature du
token et controle l'acces aux URI selon les roles declares dans conf/pie.yaml
(ou le fichier designe par PIE_CONFIG_FILE).

Deux points appellent une attention particuliere.

Ordre des middlewares
---------------------
Starlette insere chaque middleware en tete de pile : le dernier ``add_middleware``
appele se retrouve en position la plus externe. CORSMiddleware DOIT rester externe
par rapport a exa-pie, sinon les preflights OPTIONS, depourvus d'en-tete
Authorization, sont rejetes en 400 avant que CORS ait pu y repondre, et le front
ne peut plus appeler l'API. ``uris-by-roles`` ne discriminant pas la methode HTTP,
il n'existe aucun moyen d'exclure les OPTIONS par la configuration : l'ordre de
montage est le seul levier. install_jwt_middleware doit donc etre appele AVANT
l'ajout de CORSMiddleware.

Import tardif d'exa_pie
-----------------------
Le module exa_pie n'est importe qu'au moment ou le middleware est reellement
monte. Quand API_DISABLE_JWT_VALIDATION est actif, l'application demarre sans
que le connecteur soit installe, ce qui permet de travailler et de faire tourner
les tests sans acces au Pypi interne.
"""

from typing import TYPE_CHECKING

from adam_api.core.config import settings
from adam_core.utils.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


def install_jwt_middleware(app: "FastAPI") -> bool:
    """Monte le middleware exa-pie sur l'application, sauf bypass DEV.

    A appeler avant l'ajout de CORSMiddleware (cf. docstring du module).
    Retourne True si le middleware a ete monte, False s'il a ete court-circuite.
    """
    if settings.api_disable_jwt_validation:
        logger.critical(
            "JWT BYPASS actif : la validation du token est desactivee et toutes "
            "les routes sont accessibles sans authentification. "
            "Ne jamais utiliser en production."
        )
        return False

    # Import tardif volontaire : exa_pie n'est requis que si la validation est active.
    from exa_pie.middleware.fastapi import PIEFastAPIMiddleware

    app.add_middleware(PIEFastAPIMiddleware)
    logger.info("Validation JWT active : middleware exa-pie monte")
    return True
