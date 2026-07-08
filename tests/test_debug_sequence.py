from __future__ import annotations

from pathlib import Path

from tests.test_debug_session import FakeDebugAdapter

from ai_mcu_debug.runner.debug_sequence import DebugSequenceSession


def test_debug_sequence_uses_one_connection_for_multiple_operations(tmp_path: Path) -> None:
    adapter = FakeDebugAdapter()
    sequence = [
        {"operation": "reset", "params": {"halt": True}},
        {"operation": "step", "params": {}},
        {"operation": "read-register", "params": {"register": "pc"}},
        {"operation": "read-memory", "params": {"address": "0x20000000", "length": 4}},
    ]

    report = DebugSequenceSession(adapter, tmp_path).run("seq", sequence)

    assert report["ok"] is True
    assert [operation["result"]["operation"] for operation in report["operations"]] == [
        "reset",
        "step",
        "read-register",
        "read-memory",
    ]
    assert adapter.calls == ["connect", "reset:True", "step", "reg:pc", "mem:536870912:4", "close"]
    assert (tmp_path / "seq_debug_sequence.json").exists()
