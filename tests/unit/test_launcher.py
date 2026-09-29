"""Tests unitaires launcher.py"""

import io
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


def test_rejects_unknown_target() -> None:
    with pytest.raises(SystemExit) as exc_info:
        launcher.main(["unknown"])
    assert exc_info.value.code == 2


class _FakeProcess:
    """Processus fils simule : `exit_after` appels a poll() avant de s'arreter."""

    def __init__(self, exit_after: int | None, returncode: int = 0, output: bytes = b"") -> None:
        self.stdout = io.BytesIO(output)
        self._exit_after = exit_after
        self._final_code = returncode
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        if self._exit_after is not None:
            if self._exit_after == 0:
                self.returncode = self._final_code
            else:
                self._exit_after -= 1
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout: float | None = None) -> int:
        # Un fils qui a recu Ctrl+C s'arrete de lui-meme.
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:  # pragma: no cover - jamais atteint ici
        self.returncode = -9


def _patch_children(monkeypatch: pytest.MonkeyPatch, *children: _FakeProcess) -> list[list[str]]:
    commands: list[list[str]] = []
    remaining = list(children)

    def fake_popen(command: list[str], **_kwargs: Any) -> _FakeProcess:
        commands.append(command)
        return remaining.pop(0)

    monkeypatch.setattr("launcher.subprocess.Popen", fake_popen)
    monkeypatch.setattr("launcher.time.sleep", lambda _seconds: None)
    return commands


@pytest.mark.parametrize("argv", [[], ["all"]])
def test_all_starts_api_and_worker_as_children(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    commands = _patch_children(monkeypatch, _FakeProcess(0), _FakeProcess(0))

    assert launcher.main(argv) == 0
    assert [command[-1] for command in commands] == ["api", "worker"]


def test_all_prefixes_each_child_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = _FakeProcess(0, output="Uvicorn démarre\n".encode())
    worker = _FakeProcess(0, output=b"PageImageWorker demarre\r\nConsensusWorker demarre\n")
    _patch_children(monkeypatch, api, worker)

    launcher.main([])

    lines = capsys.readouterr().out.splitlines()
    assert "[api]    Uvicorn démarre" in lines
    assert "[worker] PageImageWorker demarre" in lines
    assert "[worker] ConsensusWorker demarre" in lines


def test_all_stops_api_when_worker_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    api, worker = _FakeProcess(None), _FakeProcess(1, returncode=1)
    _patch_children(monkeypatch, api, worker)

    assert launcher.main(["all"]) == 1
    assert api.terminated


def test_all_lets_children_stop_on_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    api, worker = _FakeProcess(None), _FakeProcess(None)
    _patch_children(monkeypatch, api, worker)

    def interrupted_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("launcher.time.sleep", interrupted_sleep)

    assert launcher.main(["all"]) == 0
    assert not api.terminated and not worker.terminated
