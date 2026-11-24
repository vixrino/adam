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


@pytest.mark.asyncio
async def test_stop_ends_run_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    """stop() sort proprement de run_forever a la fin du cycle en cours."""

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("adam_worker.base_worker.asyncio.sleep", fake_sleep)

    worker = _RecordingWorker([None, None, None])

    # au 2e cycle, on demande l'arret : la boucle doit s'arreter apres
    async def poll_then_stop() -> None:
        worker.calls += 1
        if worker.calls == 2:
            worker.stop()

    monkeypatch.setattr(worker, "poll", poll_then_stop)

    await worker.run_forever()

    assert worker.calls == 2
    assert worker._is_running is False


# -- Delai lu en base (app_setting) ----------------------------------------------------


class _SlowWorker(BaseWorker):
    poll_interval_seconds = 7.0

    async def poll(self) -> None:
        return None


def _store(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    async def load(*_a: object, **_k: object) -> dict:
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]

    monkeypatch.setattr("adam_worker.base_worker.settings_store.load", load)


@pytest.mark.asyncio
async def test_interval_read_from_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _store(monkeypatch, {"worker._SlowWorker.poll_interval": 42})
    assert await _SlowWorker()._current_interval() == 42.0


@pytest.mark.asyncio
async def test_interval_is_clamped_to_one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    _store(monkeypatch, {"worker._SlowWorker.poll_interval": 0})
    assert await _SlowWorker()._current_interval() == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["abc", None, True, float("nan"), [3]])
async def test_interval_invalid_or_missing_falls_back(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    _store(monkeypatch, {"worker._SlowWorker.poll_interval": value})
    assert await _SlowWorker()._current_interval() == 7.0


@pytest.mark.asyncio
async def test_interval_falls_back_when_store_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    _store(monkeypatch, RuntimeError("base injoignable"))
    assert await _SlowWorker()._current_interval() == 7.0


@pytest.mark.asyncio
async def test_run_forever_sleeps_the_stored_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    _store(monkeypatch, {"worker._SlowWorker.poll_interval": 30})
    slept: List[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise _StopLoop()

    monkeypatch.setattr("adam_worker.base_worker.asyncio.sleep", fake_sleep)
    with pytest.raises(_StopLoop):
        await _SlowWorker().run_forever()
    assert slept == [30.0]
