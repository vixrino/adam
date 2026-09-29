"""Tests unitaires launcher.py"""

from typing import Any, Dict

import pytest

import launcher


def test_api_starts_uvicorn_on_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    from adam_api.core.config import settings

    calls: Dict[str, Any] = {}

    def fake_run(app: str, **kwargs: Any) -> None:
        calls["app"] = app
        calls.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)

    assert launcher.main(["api"]) == 0
    assert calls["app"] == "adam_api.main:app"
    assert calls["host"] == settings.api_host
    assert calls["port"] == settings.api_port
    assert calls["log_config"] is None


def test_worker_runs_every_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    started = {"n": 0}

    async def fake_main() -> None:
        started["n"] += 1

    monkeypatch.setattr("adam_worker.main.main", fake_main)

    assert launcher.main(["worker"]) == 0
    assert started["n"] == 1


def test_worker_swallows_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    async def interrupted_main() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("adam_worker.main.main", interrupted_main)

    assert launcher.main(["worker"]) == 0


@pytest.mark.parametrize("argv", [[], ["unknown"]])
def test_rejects_missing_or_unknown_target(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        launcher.main(argv)
    assert exc_info.value.code == 2
