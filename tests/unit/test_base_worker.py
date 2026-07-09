"""Tests unitaires adam_worker/base_worker.py"""

from typing import List

import pytest

from adam_worker.base_worker import BaseWorker


class _StopLoop(Exception):
    """Sentinelle pour sortir de la boucle infinie de run_forever dans les tests."""


class _RecordingWorker(BaseWorker):
    poll_interval_seconds = 0.0

    def __init__(self, poll_side_effects: List[object]) -> None:
        super().__init__()
        self.calls = 0
        self._effects = list(poll_side_effects)

    async def poll(self) -> None:
        self.calls += 1
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect


@pytest.mark.asyncio
async def test_run_forever_calls_poll_and_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls = {"n": 0}

    async def fake_sleep(_seconds: float) -> None:
        sleep_calls["n"] += 1
        if sleep_calls["n"] == 2:
            raise _StopLoop()

    monkeypatch.setattr("adam_worker.base_worker.asyncio.sleep", fake_sleep)

    worker = _RecordingWorker([None, None])
    with pytest.raises(_StopLoop):
        await worker.run_forever()

    assert worker.calls == 2
    assert sleep_calls["n"] == 2


@pytest.mark.asyncio
async def test_run_forever_survives_poll_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls = {"n": 0}

    async def fake_sleep(_seconds: float) -> None:
        sleep_calls["n"] += 1
        if sleep_calls["n"] == 2:
            raise _StopLoop()

    monkeypatch.setattr("adam_worker.base_worker.asyncio.sleep", fake_sleep)

    worker = _RecordingWorker([RuntimeError("boom"), None])
    with pytest.raises(_StopLoop):
        await worker.run_forever()

    # poll() a bien ete rappele malgre l'exception du premier cycle
    assert worker.calls == 2


def test_base_worker_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseWorker()  # type: ignore[abstract]
