from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.interfaces import DebugAdapter
from ai_mcu_debug.models import Breakpoint, DebugTask, MemoryBlock, RegisterValue
from ai_mcu_debug.runner import AutoDebugSession


class FakeDebugAdapter(DebugAdapter):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def connect(self) -> None:
        self.calls.append("connect")

    def close(self) -> None:
        self.calls.append("close")

    def halt(self) -> None:
        self.calls.append("halt")

    def resume(self) -> None:
        self.calls.append("resume")

    def wait_for_stop(self, timeout_s: float = 10.0) -> str:
        self.calls.append(f"wait:{timeout_s}")
        return '*stopped,reason="breakpoint-hit"\n'

    def step(self) -> None:
        self.calls.append("step")

    def reset(self, halt: bool = True) -> None:
        self.calls.append(f"reset:{halt}")

    def set_breakpoint(self, location: str) -> Breakpoint:
        self.calls.append(f"break:{location}")
        return Breakpoint(id="1", location=location)

    def delete_breakpoint(self, breakpoint_id: str) -> None:
        self.calls.append(f"delete:{breakpoint_id}")

    def read_register(self, name: str) -> RegisterValue:
        self.calls.append(f"reg:{name}")
        values = {
            "pc": 0x08000100,
            "sp": 0x20001000,
            "lr": 0xFFFFFFFD,
            "xpsr": 0x01000000,
        }
        return RegisterValue(name=name, value=values.get(name.lower(), 0x08000100))

    def write_register(self, name: str, value: int) -> None:
        self.calls.append(f"write_reg:{name}:{value}")

    def read_memory(self, address: int, length: int) -> MemoryBlock:
        self.calls.append(f"mem:{address}:{length}")
        return MemoryBlock(address=address, data=bytes(range(length)))

    def write_memory(self, address: int, data: bytes) -> None:
        self.calls.append(f"write_mem:{address}:{len(data)}")


class FailingConnectAdapter(FakeDebugAdapter):
    def connect(self) -> None:
        self.calls.append("connect")
        raise RuntimeError("probe not connected")

    def diagnostics(self) -> dict[str, object]:
        return {"server_output_tail": ["no device found"]}


def test_auto_debug_session_runs_task_and_writes_report(tmp_path: Path) -> None:
    adapter = FakeDebugAdapter()
    task = DebugTask(
        name="smoke",
        breakpoints=["main"],
        registers=["pc", "sp", "xpsr"],
        memory_reads=[(0x20000000, 4)],
        step_count=2,
        break_timeout_s=3.0,
        record_path=tmp_path / "records.jsonl",
    )

    report = AutoDebugSession(adapter, tmp_path).run(task)

    assert report["ok"] is True
    assert report["registers"]["pc"] == "0x8000100"
    assert report["memory"][0]["data_hex"] == "00010203"
    assert report["conclusions"]
    assert adapter.calls == [
        "connect",
        "reset:True",
        "break:main",
        "resume",
        "wait:3.0",
        "step",
        "wait:3.0",
        "step",
        "wait:3.0",
        "reg:pc",
        "reg:sp",
        "reg:xpsr",
        "mem:536870912:4",
        "close",
    ]
    assert (tmp_path / "smoke.json").exists()
    assert (tmp_path / "records.jsonl").read_text(encoding="utf-8")


def test_auto_debug_session_writes_report_on_connect_failure(tmp_path: Path) -> None:
    adapter = FailingConnectAdapter()
    task = DebugTask(name="connect_failure", registers=["pc"])

    report = AutoDebugSession(adapter, tmp_path).run(task)

    assert report["ok"] is False
    assert "probe not connected" in report["error"]
    assert report["diagnostics"]["server_output_tail"] == ["no device found"]
    assert report["failure_analysis"]["probable_causes"] == ["debug_probe_not_found"]
    assert adapter.calls == ["connect", "close"]
    assert (tmp_path / "connect_failure.json").exists()


class VectorLaunchDebugAdapter(FakeDebugAdapter):
    def read_memory(self, address: int, length: int) -> MemoryBlock:
        self.calls.append(f"mem:{address}:{length}")
        if address == 0x08000000 and length == 8:
            return MemoryBlock(
                address=address,
                data=(0x20000670).to_bytes(4, "little") + (0x080001CD).to_bytes(4, "little"),
            )
        return MemoryBlock(address=address, data=bytes(range(length)))


def test_auto_debug_session_can_launch_from_vector_table(tmp_path: Path) -> None:
    adapter = VectorLaunchDebugAdapter()
    task = DebugTask(
        name="vector_launch",
        breakpoints=["main"],
        registers=["pc"],
        reset_before_run=True,
        launch_from_vector_table=0x08000000,
    )

    report = AutoDebugSession(adapter, tmp_path).run(task)

    assert report["ok"] is True
    assert report["launch"]["initial_sp"] == "0x20000670"
    assert report["launch"]["reset_handler"] == "0x80001cd"
    assert "launch_from_vector_table" in report["events"]
    assert adapter.calls[:6] == [
        "connect",
        "reset:True",
        "mem:134217728:8",
        "write_reg:sp:536872560",
        "write_reg:pc:134218189",
        "break:main",
    ]
