from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.hardware_identity import CPUID_ADDRESS, STM32_DBGMCU_IDCODE_ADDRESS, read_hardware_identity
from ai_mcu_debug.models import MemoryBlock
from tests.test_debug_session import FakeDebugAdapter


class IdentityDebugAdapter(FakeDebugAdapter):
    def read_memory(self, address: int, length: int) -> MemoryBlock:
        self.calls.append(f"mem:{address}:{length}")
        values = {
            CPUID_ADDRESS: 0x410FC231,
            STM32_DBGMCU_IDCODE_ADDRESS: 0x10030414,
        }
        if address not in values:
            raise RuntimeError(f"unexpected address 0x{address:x}")
        return MemoryBlock(address=address, data=values[address].to_bytes(length, "little"))


class CpuidOnlyDebugAdapter(FakeDebugAdapter):
    def read_memory(self, address: int, length: int) -> MemoryBlock:
        self.calls.append(f"mem:{address}:{length}")
        if address == CPUID_ADDRESS:
            return MemoryBlock(address=address, data=(0x410FC241).to_bytes(length, "little"))
        raise RuntimeError("DBGMCU not present")


def test_read_hardware_identity_decodes_cortex_m_and_stm32_id(tmp_path: Path) -> None:
    adapter = IdentityDebugAdapter()

    report = read_hardware_identity(adapter, report_dir=tmp_path, expected_chip="STM32F103RCT6")

    assert report["ok"] is True
    assert report["decoded"]["cortex_m_cpuid"]["part_name"] == "Cortex-M3"
    assert report["decoded"]["stm32_dbgmcu_idcode"]["dev_id"] == "0x414"
    assert report["decoded"]["stm32_dbgmcu_idcode"]["line"] == "STM32F10x high-density"
    assert report["expected_chip_check"]["compatible"] is True
    assert (tmp_path / "hardware_identity.json").exists()
    assert adapter.calls == [
        "connect",
        "halt",
        f"mem:{CPUID_ADDRESS}:4",
        f"mem:{STM32_DBGMCU_IDCODE_ADDRESS}:4",
        "close",
    ]


def test_read_hardware_identity_keeps_partial_cortex_m_evidence(tmp_path: Path) -> None:
    report = read_hardware_identity(CpuidOnlyDebugAdapter(), report_dir=tmp_path, expected_chip="STM32F103RCT6")

    assert report["ok"] is True
    assert report["decoded"]["cortex_m_cpuid"]["part_name"] == "Cortex-M4"
    assert report["status"] == "partial"
    assert any(item["kind"] == "expected_chip_not_verified" for item in report["uncertain"])
