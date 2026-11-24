"""Lecture et ecriture de la table APP_SETTING (configuration modifiable a chaud).

Pas de cache : chaque appelant relit la base quand il en a besoin (un cycle de
worker, une requete), donc une modification vaut des le cycle suivant.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adam_core.db.session import get_async_session
from adam_core.models.app_setting import AppSetting

#: Dernier ping du moteur OCR, ecrit par le worker de pre-alimentation : {"reachable": bool}.
OCR_STATUS_KEY = "ocr_status"


async def load(db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Toutes les cles en un seul SELECT. Ouvre sa propre session si `db` est absent."""
    if db is None:
        async with get_async_session() as session:
            return await load(session)
    rows = (await db.execute(select(AppSetting.key, AppSetting.value))).all()
    return {key: value for key, value in rows}


async def set_value(
    db: AsyncSession, key: str, value: Any, updated_by: Optional[str] = None
) -> None:
    """Cree ou met a jour une cle. Le commit reste a l'appelant."""
    stmt = insert(AppSetting).values(key=key, value=value, updated_by=updated_by)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"value": stmt.excluded.value, "updated_by": stmt.excluded.updated_by},
        )
    )


async def rows(db: AsyncSession) -> List[AppSetting]:
    """Les lignes completes (valeur, date et auteur de la derniere modification)."""
    return list((await db.execute(select(AppSetting).order_by(AppSetting.key))).scalars().all())


async def delete(db: AsyncSession, key: str) -> bool:
    """Supprime une cle ; faux si elle n'existait pas. Le commit reste a l'appelant."""
    result = await db.execute(sa_delete(AppSetting).where(AppSetting.key == key))
    return bool(result.rowcount)
