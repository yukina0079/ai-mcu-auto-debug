from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def validate_debug_target(target_path: Path, probe_report: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.loads(target_path.read_text(encoding="utf-8"))
    command = [str(item) for item in data.get("server_command") or []]
    backend = data.get("backend")
    interface = _detect_openocd_interface(command)
    target_cfg = _detect_target_cfg(command)
    transport = _detect_transport(command)
    probe_kinds = _probe_kinds(probe_report or {})
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if backend == "openocd-gdb" and not command:
        errors.append({"code": "missing_server_command", "message": "OpenOCD target config has no server_command."})

    if "cmsis-dap" in probe_kinds and interface == "stlink":
        warnings.append(
            {
                "code": "probe_interface_mismatch",
                "message": "CMSIS-DAP/DAPLink probe is detected, but target config uses interface/stlink.cfg.",
                "expected_interface": "interface/cmsis-dap.cfg",
            }
        )
    if "stlink" in probe_kinds and interface == "cmsis-dap":
        warnings.append(
            {
                "code": "probe_interface_mismatch",
                "message": "ST-Link probe is detected, but target config uses interface/cmsis-dap.cfg.",
                "expected_interface": "interface/stlink.cfg",
            }
        )

    if backend == "openocd-gdb" and target_cfg and "stm32f1x.cfg" not in target_cfg.lower():
        warnings.append(
            {
                "code": "target_family_check_required",
                "message": "Target config is not target/stm32f1x.cfg; verify it matches STM32F103.",
                "target_cfg": target_cfg,
            }
        )

    if backend == "openocd-gdb" and interface == "cmsis-dap" and transport != "swd":
        warnings.append(
            {
                "code": "transport_not_explicitly_swd",
                "message": "CMSIS-DAP config should explicitly select SWD for STM32 SWD attach.",
            }
        )

    return {
        "ok": not errors,
        "target": str(target_path),
        "backend": backend,
        "interface": interface,
        "target_cfg": target_cfg,
        "transport": transport,
        "probe_kinds": sorted(probe_kinds),
        "warnings": warnings,
        "errors": errors,
    }


def _detect_openocd_interface(command: list[str]) -> str | None:
    joined = " ".join(command).lower().replace("\\", "/")
    if "interface/cmsis-dap.cfg" in joined:
        return "cmsis-dap"
    if "interface/stlink.cfg" in joined:
        return "stlink"
    if "interface/jlink.cfg" in joined:
        return "jlink"
    if "interface/" in joined:
        return "other"
    return None


def _detect_target_cfg(command: list[str]) -> str | None:
    normalized = [item.replace("\\", "/") for item in command]
    for index, item in enumerate(normalized):
        if item == "-f" and index + 1 < len(normalized) and normalized[index + 1].startswith("target/"):
            return normalized[index + 1]
    return None


def _detect_transport(command: list[str]) -> str | None:
    joined = " ".join(command).lower()
    if "transport select swd" in joined:
        return "swd"
    if "transport select jtag" in joined:
        return "jtag"
    return None


def _probe_kinds(report: dict[str, Any]) -> set[str]:
    kinds: set[str] = set()
    for probe in report.get("probes", []):
        text = " ".join(
            str(value)
            for value in [
                probe.get("friendly_name"),
                probe.get("instance_id"),
                " ".join(probe.get("matched_usb_ids", [])),
                " ".join(probe.get("matched_keywords", [])),
            ]
            if value
        ).lower()
        if any(token in text for token in ("cmsis-dap", "daplink", "vid_c251&pid_f001")):
            kinds.add("cmsis-dap")
        if "st-link" in text or "stlink" in text:
            kinds.add("stlink")
        if "j-link" in text or "jlink" in text:
            kinds.add("jlink")
    return kinds
