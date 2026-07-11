from __future__ import annotations

import subprocess
from pathlib import Path

from ai_mcu_debug.adapters.gdb_remote import GdbRemoteAdapter
from ai_mcu_debug.models import DebugTargetConfig


class FakeStream:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, *, requires_kill: bool = False) -> None:
        self.stdin = FakeStream()
        self.stdout = FakeStream()
        self.stderr = FakeStream()
        self.requires_kill = requires_kill
        self.running = True
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self) -> int | None:
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated = True
        if not self.requires_kill:
            self.running = False

    def kill(self) -> None:
        self.killed = True
        self.running = False

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.running:
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0


def test_terminate_process_waits_and_closes_pipes(tmp_path: Path) -> None:
    adapter = GdbRemoteAdapter(DebugTargetConfig(backend="gdb-remote", log_path=tmp_path / "commands.jsonl"))
    process = FakeProcess(requires_kill=True)

    adapter._terminate_process(process)  # type: ignore[arg-type]

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True
