"""Sondes /health (vivacite) et /health/ready (disponibilite)."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
import pytest

from adam_api import main


class _Conn:
    def __init__(self, error: Exception | None) -> None:
        self._error = error

    async def execute(self, _statement: Any) -> None:
        if self._error:
            raise self._error


class _Engine:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_Conn]:
        yield _Conn(self._error)


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_vivacite_ne_divulgue_rien_et_ignore_la_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_engine", lambda: pytest.fail("la base ne doit pas etre touchee"))
    response = await _get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_disponibilite_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_engine", lambda: _Engine())
    response = await _get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


@pytest.mark.asyncio
async def test_disponibilite_503_sans_fuite_du_motif(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_engine", lambda: _Engine(OSError("connexion a db-prod:5432")))
    response = await _get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "error"}}
    assert "db-prod" not in response.text
