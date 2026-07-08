from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.adapters.gdb_remote import GdbRemoteAdapter
from ai_mcu_debug.models import DebugTargetConfig


class RecoveringGdbAdapter(GdbRemoteAdapter):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(
            DebugTargetConfig(
                backend="gdb-remote",
                log_path=tmp_path / "commands.jsonl",
                command_retries=2,
                recover_on_disconnect=True,
            )
        )
        self.sends = 0
        self.recoveries = 0

    def _send_and_collect(self, line: str, token: int) -> str:
        self.sends += 1
        if self.sends == 1:
            raise RuntimeError("GDB exited unexpectedly")
        return f"{token}^done\n"

    def _recover_connection(self) -> None:
        self.recoveries += 1


def test_mi_command_recovers_once_after_disconnect(tmp_path: Path) -> None:
    adapter = RecoveringGdbAdapter(tmp_path)

    output = adapter._mi("-data-list-register-values x", "read_registers", {})

    assert output.endswith("^done\n")
    assert adapter.sends == 2
    assert adapter.recoveries == 1


class ConnectedResultGdbAdapter(GdbRemoteAdapter):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(DebugTargetConfig(backend="gdb-remote", log_path=tmp_path / "commands.jsonl"))

    def _send_and_collect(self, line: str, token: int) -> str:
        return f'{token}^connected\n*stopped,reason="signal-received"\n'


def test_mi_accepts_target_select_connected_result(tmp_path: Path) -> None:
    adapter = ConnectedResultGdbAdapter(tmp_path)

    output = adapter._mi_once("-target-select extended-remote localhost:3333", "connect", {})

    assert output.startswith("1^connected")
