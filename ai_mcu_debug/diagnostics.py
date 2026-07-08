from __future__ import annotations

import re
from typing import Any


def analyze_debug_failure(error: str, diagnostics: dict[str, Any]) -> dict[str, object]:
    server_tail = "\n".join(str(line) for line in diagnostics.get("server_output_tail", []))
    combined = f"{error}\n{server_tail}".lower()
    causes: list[str] = []
    next_actions: list[str] = []

    if "error: open failed" in combined or "open failed" in combined:
        causes.append("debug_probe_open_failed")
        next_actions.extend(
            [
                "Check that the ST-Link/J-Link/CMSIS-DAP probe is connected over USB.",
                "Check probe driver permissions and whether another program is using the probe.",
                "Check that the OpenOCD interface config matches the probe, for example interface/stlink.cfg.",
            ]
        )

    if "no device found" in combined or "no cmsis-dap device found" in combined:
        causes.append("debug_probe_not_found")
        next_actions.append("Reconnect the debug probe and verify it appears in Device Manager.")

    if "couldn't bind" in combined or "address already in use" in combined:
        causes.append("gdb_server_port_in_use")
        next_actions.append("Stop the existing GDB/OpenOCD process or change the remote port.")

    if "already open" in combined or "probe is already in use" in combined:
        causes.append("debug_probe_already_open")
        next_actions.append("Close the other OpenOCD/pyOCD/J-Link session using the probe, then retry the read-only attach.")

    if "target voltage" in combined:
        causes.append("target_power_issue")
        next_actions.append("Check that the MCU board is powered and SWD pins share ground with the probe.")

    if "cannot read idr" in combined or "error connecting dp" in combined or "no ack" in combined:
        causes.append("swd_target_dp_not_responding")
        next_actions.extend(
            [
                "Probe USB is visible, but the SWD target did not answer DP IDR reads.",
                "Check target power, common GND, SWDIO, SWCLK, NRST, BOOT0 state, and whether the MCU is held in reset.",
                "Try a lower adapter speed and connect-under-reset if the target firmware disables SWD or enters low power.",
            ]
        )

    reset_state = _extract_openocd_reset_state(server_tail)
    if reset_state and reset_state.get("nRESET") == 0:
        extra = diagnostics.get("extra", {})
        nrst_connected = extra.get("nrst_connected") if isinstance(extra, dict) else None
        if nrst_connected is False:
            causes.append("target_reset_line_not_connected")
            next_actions.append("OpenOCD sampled nRESET=0, but target config records NRST is not connected; do not treat this as proof that the MCU is held in reset.")
        else:
            causes.append("target_reset_line_held_low")
            next_actions.extend(
                [
                    "OpenOCD sampled nRESET=0; verify NRST is not shorted, held by the reset button/capacitor, or wired to the wrong probe pin.",
                    "Measure the target NRST pin directly. It should normally be high when the board is not being reset.",
                ]
            )

    if "0x1ffff" in combined and "target did not stop" in combined:
        causes.append("target_running_from_system_memory")
        next_actions.extend(
            [
                "PC is in STM32 system memory after reset; check BOOT0/BOOT1 pins or flash a user firmware image before waiting for main().",
                "If boot pins are intentional, use a debug task that reads registers/memory without waiting for a user-code breakpoint.",
            ]
        )

    if "cmsis-dap command mismatch" in combined:
        causes.append("cmsis_dap_protocol_or_firmware_issue")
        next_actions.append("Try pyOCD or update the DAPLink/CMSIS-DAP firmware if OpenOCD command mismatch repeats.")

    if "unable to find a matching cmsis-dap device" in combined:
        causes.append("cmsis_dap_probe_not_found")
        next_actions.append("Use a CMSIS-DAP OpenOCD interface config or install the probe driver.")

    if not causes:
        causes.append("unknown_debug_connection_failure")
        next_actions.append("Inspect diagnostics.server_output_tail and verify target_gdb, server_command, and wiring.")

    return {
        "probable_causes": _dedupe(causes),
        "next_actions": _dedupe(next_actions),
        "observations": _drop_none({"openocd_reset_state": reset_state}),
    }


def _extract_openocd_reset_state(text: str) -> dict[str, int] | None:
    matches = re.findall(r"\b(SWCLK/TCK|SWDIO/TMS|TDI|TDO|nTRST|nRESET)\s*=\s*([01])", text)
    if not matches:
        return None
    return {name: int(value) for name, value in matches}


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
