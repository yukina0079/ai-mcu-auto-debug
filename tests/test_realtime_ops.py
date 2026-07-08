from __future__ import annotations

from tests.test_debug_session import FakeDebugAdapter

from ai_mcu_debug.runner.realtime_ops import execute_debug_operation


def test_execute_read_register_operation() -> None:
    adapter = FakeDebugAdapter()

    report = execute_debug_operation(adapter, "read-register", {"register": "pc"})

    assert report == {
        "ok": True,
        "operation": "read-register",
        "register": "pc",
        "value": "0x8000100",
    }
    assert adapter.calls == ["reg:pc"]


def test_execute_write_memory_operation() -> None:
    adapter = FakeDebugAdapter()

    report = execute_debug_operation(
        adapter,
        "write-memory",
        {"address": "0x20000000", "data_hex": "01020304"},
    )

    assert report == {"ok": True, "operation": "write-memory"}
    assert adapter.calls == ["write_mem:536870912:4"]


def test_execute_mapped_peripheral_register_read_as_memory() -> None:
    adapter = FakeDebugAdapter()

    report = execute_debug_operation(
        adapter,
        "read-register",
        {
            "register": "GPIOC.CRH",
            "mapped_register": {
                "qualified_name": "GPIOC.CRH",
                "address": 0x40011004,
                "size_bytes": 4,
            },
        },
    )

    assert report == {
        "ok": True,
        "operation": "read-register",
        "register": "GPIOC.CRH",
        "address": "0x40011004",
        "value": "0x3020100",
        "data_hex": "00010203",
    }
    assert adapter.calls == ["mem:1073811460:4"]
