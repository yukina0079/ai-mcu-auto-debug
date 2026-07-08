from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.target_validation import validate_debug_target


def test_validate_target_warns_when_daplink_uses_stlink_interface(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(
            {
                "backend": "openocd-gdb",
                "server_command": ["openocd", "-f", "interface/stlink.cfg", "-f", "target/stm32f1x.cfg"],
            }
        ),
        encoding="utf-8",
    )
    probe_report = {
        "probes": [
            {
                "friendly_name": "USB Composite Device",
                "instance_id": "USB\\VID_C251&PID_F001\\LU_2022_8888",
                "matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"],
            }
        ]
    }

    report = validate_debug_target(target, probe_report=probe_report)

    assert report["ok"] is True
    assert report["interface"] == "stlink"
    assert report["probe_kinds"] == ["cmsis-dap"]
    assert report["warnings"][0]["code"] == "probe_interface_mismatch"


def test_validate_target_accepts_cmsis_dap_stm32f1_swd_config(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(
            {
                "backend": "openocd-gdb",
                "server_command": [
                    "openocd",
                    "-f",
                    "interface/cmsis-dap.cfg",
                    "-c",
                    "transport select swd",
                    "-f",
                    "target/stm32f1x.cfg",
                ],
            }
        ),
        encoding="utf-8",
    )
    probe_report = {"probes": [{"matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"]}]}

    report = validate_debug_target(target, probe_report=probe_report)

    assert report["ok"] is True
    assert report["warnings"] == []
    assert report["interface"] == "cmsis-dap"
    assert report["transport"] == "swd"
