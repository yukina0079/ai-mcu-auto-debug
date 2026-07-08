from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.audit_log import append_audit_event
from ai_mcu_debug.interfaces import DebugAdapter


CPUID_ADDRESS = 0xE000ED00
STM32_DBGMCU_IDCODE_ADDRESS = 0xE0042000


CORTEX_M_PARTS = {
    0xC20: "Cortex-M0",
    0xC21: "Cortex-M1",
    0xC23: "Cortex-M3",
    0xC24: "Cortex-M4",
    0xC27: "Cortex-M7",
    0xC60: "Cortex-M0+",
    0xD20: "Cortex-M23",
    0xD21: "Cortex-M33",
    0xD22: "Cortex-M55",
    0xD23: "Cortex-M85",
}


STM32_DEVICES = {
    0x410: {
        "line": "STM32F10x medium-density",
        "families": ["STM32F101x8/B", "STM32F102x8/B", "STM32F103x8/B"],
        "density_codes": {"8", "B"},
    },
    0x412: {
        "line": "STM32F10x low-density",
        "families": ["STM32F101x4/6", "STM32F102x4/6", "STM32F103x4/6"],
        "density_codes": {"4", "6"},
    },
    0x414: {
        "line": "STM32F10x high-density",
        "families": ["STM32F101xC/D/E", "STM32F103xC/D/E"],
        "density_codes": {"C", "D", "E"},
    },
    0x418: {
        "line": "STM32F10x connectivity line",
        "families": ["STM32F105xx", "STM32F107xx"],
        "density_codes": set(),
    },
    0x430: {
        "line": "STM32F10x XL-density",
        "families": ["STM32F101xF/G", "STM32F103xF/G"],
        "density_codes": {"F", "G"},
    },
}


def read_hardware_identity(
    adapter: DebugAdapter,
    report_dir: Path = Path("debug_runs/hardware_identity"),
    expected_chip: str | None = None,
    halt: bool = True,
) -> dict[str, Any]:
    """Read stable read-only identification registers through the debug adapter."""

    report_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "ok": False,
        "status": "not_started",
        "expected_chip": expected_chip,
        "halt_requested": halt,
        "reads": [],
        "decoded": {},
        "inferences": [],
        "uncertain": [],
        "next_actions": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        adapter.connect()
        if halt:
            try:
                adapter.halt()
                report["halted"] = True
            except Exception as exc:  # pragma: no cover - backend-specific edge
                report["halted"] = False
                report["uncertain"].append({"kind": "halt_failed", "error": str(exc)})
        _read_identity_register(adapter, report, "cortex_m_cpuid", CPUID_ADDRESS, required=True)
        _read_identity_register(adapter, report, "stm32_dbgmcu_idcode", STM32_DBGMCU_IDCODE_ADDRESS, required=False)
    except Exception as exc:
        report["status"] = "connect_or_read_failed"
        report["error"] = str(exc)
        diagnostics = adapter.diagnostics()
        if diagnostics:
            report["diagnostics"] = diagnostics
        report["next_actions"].append("Check debug probe connection, target power, SWD/JTAG wiring, and target config.")
    finally:
        try:
            adapter.close()
        except Exception as exc:  # pragma: no cover - close should not hide read evidence
            report["close_error"] = str(exc)

    _decode_reads(report)
    _check_expected_chip(report, expected_chip)
    successful_reads = [item for item in report["reads"] if item.get("ok")]
    if successful_reads:
        report["ok"] = True
        failed_reads = [item for item in report["reads"] if not item.get("ok")]
        report["status"] = "partial" if failed_reads else "ok"
    elif report["status"] == "not_started":
        report["status"] = "read_failed"
        report["next_actions"].append("Run connection-diagnose; no hardware identity registers were readable.")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report_path = report_dir / "hardware_identity.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["report_path"] = str(report_path)
    append_audit_event(
        "hardware_identity",
        args={"expected_chip": expected_chip, "halt": halt, "report_dir": str(report_dir)},
        result={
            "status": report["status"],
            "decoded": report["decoded"],
            "inferences": report["inferences"],
            "uncertain": report["uncertain"],
        },
        ok=bool(report["ok"]),
    )
    return report


def _read_identity_register(
    adapter: DebugAdapter,
    report: dict[str, Any],
    name: str,
    address: int,
    required: bool,
) -> None:
    try:
        block = adapter.read_memory(address, 4)
        if len(block.data) < 4:
            raise ValueError(f"short read: expected 4 bytes, got {len(block.data)}")
        value = int.from_bytes(block.data[:4], "little")
        report["reads"].append(
            {
                "ok": True,
                "name": name,
                "address": f"0x{address:08x}",
                "value": f"0x{value:08x}",
                "data_hex": block.data[:4].hex(),
                "required": required,
            }
        )
    except Exception as exc:
        read = {
            "ok": False,
            "name": name,
            "address": f"0x{address:08x}",
            "error": str(exc),
            "required": required,
        }
        report["reads"].append(read)
        if required:
            report["uncertain"].append({"kind": f"{name}_unreadable", "address": read["address"], "error": str(exc)})


def _decode_reads(report: dict[str, Any]) -> None:
    values = {_read["name"]: int(str(_read["value"]), 0) for _read in report["reads"] if _read.get("ok")}
    if "cortex_m_cpuid" in values:
        report["decoded"]["cortex_m_cpuid"] = _decode_cpuid(values["cortex_m_cpuid"])
        report["inferences"].append(
            {
                "kind": "cpu_core",
                "source": "cortex_m_cpuid",
                "value": report["decoded"]["cortex_m_cpuid"].get("part_name") or "unknown_cortex_m_part",
                "confidence": "high" if report["decoded"]["cortex_m_cpuid"].get("part_name") else "low",
            }
        )
    if "stm32_dbgmcu_idcode" in values:
        decoded = _decode_stm32_dbgmcu_idcode(values["stm32_dbgmcu_idcode"])
        report["decoded"]["stm32_dbgmcu_idcode"] = decoded
        report["inferences"].append(
            {
                "kind": "stm32_device_line",
                "source": "stm32_dbgmcu_idcode",
                "value": decoded.get("line") or "unknown_stm32_device_id",
                "confidence": "medium" if decoded.get("line") else "low",
            }
        )


def _decode_cpuid(value: int) -> dict[str, Any]:
    implementer = (value >> 24) & 0xFF
    variant = (value >> 20) & 0xF
    architecture = (value >> 16) & 0xF
    part_no = (value >> 4) & 0xFFF
    revision = value & 0xF
    return {
        "raw": f"0x{value:08x}",
        "implementer": f"0x{implementer:02x}",
        "implementer_name": "ARM" if implementer == 0x41 else None,
        "variant": variant,
        "architecture": f"0x{architecture:x}",
        "part_no": f"0x{part_no:03x}",
        "part_name": CORTEX_M_PARTS.get(part_no),
        "revision": revision,
    }


def _decode_stm32_dbgmcu_idcode(value: int) -> dict[str, Any]:
    dev_id = value & 0xFFF
    rev_id = (value >> 16) & 0xFFFF
    known = STM32_DEVICES.get(dev_id, {})
    return {
        "raw": f"0x{value:08x}",
        "dev_id": f"0x{dev_id:03x}",
        "rev_id": f"0x{rev_id:04x}",
        "line": known.get("line"),
        "families": known.get("families", []),
        "density_codes": sorted(known.get("density_codes", set())),
    }


def _check_expected_chip(report: dict[str, Any], expected_chip: str | None) -> None:
    if not expected_chip:
        return
    normalized = expected_chip.upper().replace("_", "").replace("-", "")
    decoded = report["decoded"].get("stm32_dbgmcu_idcode")
    if not decoded:
        report["uncertain"].append(
            {
                "kind": "expected_chip_not_verified",
                "expected_chip": expected_chip,
                "reason": "stm32_dbgmcu_idcode_unavailable",
            }
        )
        return
    density_code = _stm32_density_code(normalized)
    density_codes = set(decoded.get("density_codes", []))
    compatible = bool(
        normalized.startswith("STM32F10")
        and str(decoded.get("line") or "").startswith("STM32F10x")
        and (not density_codes or density_code in density_codes)
    )
    report["expected_chip_check"] = {
        "expected_chip": expected_chip,
        "compatible": compatible,
        "basis": "STM32 DBGMCU_IDCODE device line and density code",
        "note": "This verifies device line/density, not exact package, flash marking, or board identity.",
    }
    if not compatible:
        report["uncertain"].append(
            {
                "kind": "expected_chip_mismatch_or_unverified",
                "expected_chip": expected_chip,
                "observed_line": decoded.get("line"),
                "observed_density_codes": decoded.get("density_codes", []),
            }
        )


def _stm32_density_code(chip: str) -> str | None:
    import re

    match = re.match(r"STM32[A-Z]?\d{3}[A-Z]([0-9A-Z])", chip)
    return match.group(1) if match else None
