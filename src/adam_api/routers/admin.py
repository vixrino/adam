"""Zone /admin : reglages a chaud (app_setting), variables d'environnement, outils d'exploitation.

Reserve aux administrateurs NOTA : le groupe AD est filtre par le middleware (conf/pie.yaml,
`/api/v1/admin`), le role de plateforme (NOTA_ADMIN, table `user`) par la route elle-meme, comme
le retrait d'un document. `app_setting` ne garde jamais de secret.
"""

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.core.config import settings
from adam_api.dependencies.auth import Caller, UserCaller, get_caller, require_user
from adam_api.dependencies.db import get_db
from adam_api.schemas.admin import EnvVarOut, SettingIn, SettingOut
from adam_api.services.consensus import try_resolve
from adam_core.db import settings_store
from adam_core.enums.roles import PlatformRole
from adam_core.models.app_setting import AppSetting
from adam_core.utils.exceptions import raise_forbidden, raise_not_found, raise_unprocessable
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)


async def _require_admin(caller: Caller = Depends(get_caller)) -> None:
    """Reserve la zone /admin aux administrateurs NOTA (role de plateforme NOTA_ADMIN).

    Ni le Superviseur NOTA ni un utilisateur metier ne suffisent, et les services machine sont
    refuses : la cle partagee ne doit pas ouvrir la configuration a chaud.
    """
    if not isinstance(caller, UserCaller) or caller.platform_role != PlatformRole.NOTA_ADMIN.value:
        raise_forbidden("Route reservee aux administrateurs NOTA")


router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(_require_admin)])

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_VALUE_BYTES = 10_240
#: Noms d'environnement dont la valeur n'est jamais renvoyee.
SECRET_WORDS = ("password", "key", "secret", "token")

#: Cles connues : type, defaut du code, minimum, description. Un delai de worker vaut le
#: defaut de la classe quand la cle manque (cf. BaseWorker) ; test_admin le verifie.
KNOWN_SETTINGS: Dict[str, Dict[str, Any]] = {
    "ocr_enabled": {
        "type": bool,
        "default": True,
        "description": "Moteur OCR actif ; faux : les documents restent en attente.",
    },
    "ad_enabled": {
        "type": bool,
        "default": False,
        "description": "Annuaire AD actif (la variable AD_ENABLED le force).",
    },
    settings_store.OCR_STATUS_KEY: {
        "type": dict,
        "default": None,
        "description": "Dernier ping du moteur OCR, ecrit par le worker de pre-alimentation.",
        "managed_by_worker": True,
    },
}
for _worker, _delay in (
    ("PageImageWorker", 5.0),
    ("ConsensusWorker", 5.0),
    ("PrepopulationWorker", 30.0),
    ("TestExecutionWorker", 10.0),
):
    KNOWN_SETTINGS[f"worker.{_worker}.poll_interval"] = {
        "type": (int, float),
        "default": _delay,
        "min": 1,
        "description": f"Delai en secondes entre deux cycles de {_worker}.",
    }


def _validate(key: str, value: Any) -> None:
    if value is None:
        raise_unprocessable("La valeur ne peut pas etre nulle")
    if len(json.dumps(value).encode()) > MAX_VALUE_BYTES:
        raise_unprocessable(f"Valeur trop grande (maximum {MAX_VALUE_BYTES} octets)")
    spec = KNOWN_SETTINGS.get(key)
    if spec is None:
        return
    attendu = spec["type"]
    # bool est un int en Python : un delai « true » n'est pas un nombre.
    if not isinstance(value, attendu) or (isinstance(value, bool) and attendu is not bool):
        nom = "booleen" if attendu is bool else "objet" if attendu is dict else "nombre"
        raise_unprocessable(f"{key} attend un {nom}")
    if "min" in spec and value < spec["min"]:
        raise_unprocessable(f"{key} doit etre superieur ou egal a {spec['min']}")


def _output(key: str, row: Optional[AppSetting]) -> SettingOut:
    spec = KNOWN_SETTINGS.get(key, {})
    default = spec.get("default")
    source: str
    effective: Any
    if key == "ad_enabled" and settings.ad_enabled:
        source, effective = "env", True
    elif row is not None:
        source, effective = "db", row.value
    else:
        source, effective = "default", default
    return SettingOut(
        key=key,
        value=row.value if row is not None else None,
        default=default,
        effective=effective,
        source=source,  # type: ignore[arg-type]
        description=spec.get("description"),
        updated_at=row.updated_at if row is not None else None,
        updated_by=row.updated_by if row is not None else None,
        managed_by_worker=spec.get("managed_by_worker", False),
    )


@router.get("/settings")
async def lister_reglages(db: AsyncSession = Depends(get_db)) -> List[SettingOut]:
    """Les lignes de la base, plus les cles connues qui n'en ont pas encore."""
    lignes = {r.key: r for r in await settings_store.rows(db)}
    return [_output(k, lignes.get(k)) for k in sorted({*lignes, *KNOWN_SETTINGS})]


@router.put("/settings/{key}", responses={422: {"description": "Requete invalide"}})
async def ecrire_reglage(
    key: str,
    body: SettingIn,
    caller: UserCaller = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SettingOut:
    """Cree ou met a jour une cle ; `updated_by` est le matricule de l'appelant."""
    if not KEY_PATTERN.match(key):
        raise_unprocessable("Cle invalide : lettres, chiffres, _ . - (100 caracteres au plus)")
    _validate(key, body.value)
    ancien = (await settings_store.load(db)).get(key)
    await settings_store.set_value(db, key, body.value, updated_by=caller.matricule)
    await db.commit()
    logger.info("app_setting %s : %r -> %r par %s", key, ancien, body.value, caller.matricule)
    ligne = next((r for r in await settings_store.rows(db) if r.key == key), None)
    return _output(key, ligne)


@router.delete("/settings/{key}", status_code=204, responses={404: {"description": "Introuvable"}})
async def supprimer_reglage(
    key: str,
    caller: UserCaller = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Supprime la ligne ; une cle connue retombe sur le defaut du code."""
    if not await settings_store.delete(db, key):
        raise_not_found(AppSetting, f"Reglage {key} introuvable")
    await db.commit()
    logger.info("app_setting %s supprime par %s", key, caller.matricule)
    return Response(status_code=204)


@router.get("/env")
async def lister_environnement() -> List[EnvVarOut]:
    """Variables d'environnement lues par l'API, en lecture seule ; les secrets sont masques."""
    sortie = []
    for name in type(settings).model_fields:
        valeur = getattr(settings, name)
        secret = any(mot in name for mot in SECRET_WORDS)
        sortie.append(
            EnvVarOut(
                name=name.upper(),
                value=None if secret else str(valeur),
                secret=secret,
                defined=bool(valeur) if secret else True,
                group=name.split("_", 1)[0].upper(),
            )
        )
    return sorted(sortie, key=lambda v: (v.group, v.name))


@router.post("/consensus/resolve/{document_id}")
async def force_resolve(document_id: int, dataset_id: int) -> dict[str, Any]:
    """Outil de dev : relance le consensus d'un document."""
    if not settings.is_dev:
        raise_forbidden()
    return await try_resolve(document_id, dataset_id)
