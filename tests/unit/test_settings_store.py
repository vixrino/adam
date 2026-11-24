"""Tests unitaires adam_core/db/settings_store.py (sans base)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from adam_core.db import settings_store


def _db(rows: list[tuple[str, Any]]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    return db


async def test_load_returns_key_value_dict_in_one_select() -> None:
    db = _db([("ocr_enabled", True), ("worker.X.poll_interval", 12)])
    assert await settings_store.load(db) == {"ocr_enabled": True, "worker.X.poll_interval": 12}
    db.execute.assert_awaited_once()


async def test_load_opens_its_own_session_when_none_given(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db([("ad_enabled", False)])

    class _Ctx:
        async def __aenter__(self) -> AsyncMock:
            return db

        async def __aexit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr(settings_store, "get_async_session", lambda: _Ctx())
    assert await settings_store.load() == {"ad_enabled": False}


async def test_set_value_is_an_upsert() -> None:
    db = AsyncMock()
    await settings_store.set_value(db, "ocr_enabled", False, updated_by="V654846")
    stmt = db.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (key) DO UPDATE" in sql
    assert "app_setting" in sql
