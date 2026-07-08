from __future__ import annotations

import json
import platform
import subprocess
from typing import Any


KNOWN_PROBE_KEYWORDS = (
    "st-link",
    "stlink",
    "j-link",
    "jlink",
    "cmsis-dap",
    "daplink",
    "mbed",
    "ulink",
    "black magic",
    "debug probe",
)

KNOWN_PROBE_USB_IDS = {
    "vid_c251&pid_f001": "CMSIS-DAP/DAPLink compatible probe",
    "vid_0d28&pid_0204": "DAPLink compatible probe",
    "vid_0d28&pid_0205": "DAPLink compatible probe",
    "vid_0d28&pid_0206": "DAPLink compatible probe",
    "vid_0483&pid_3748": "ST-Link debug probe",
    "vid_0483&pid_374b": "ST-Link debug probe",
    "vid_0483&pid_374e": "ST-Link debug probe",
    "vid_1366": "J-Link debug probe",
}


def scan_debug_probes() -> dict[str, Any]:
    if platform.system().lower() == "windows":
        devices = _scan_windows_pnp_devices()
    else:
        devices = []
    probes = [_classify_device(device) for device in devices]
    probes = [probe for probe in probes if probe["matched"]]
    return {
        "ok": bool(probes),
        "platform": platform.system(),
        "probes": probes,
        "device_count": len(devices),
        "recommendations": _recommendations(probes),
    }


def _scan_windows_pnp_devices() -> list[dict[str, Any]]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-PnpDevice -PresentOnly | "
            "Select-Object FriendlyName,InstanceId,Class,Status | "
            "ConvertTo-Json -Depth 2"
        ),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    stdout = completed.stdout or ""
    if completed.returncode != 0 or not stdout.strip():
        return []
    parsed = json.loads(stdout)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _classify_device(device: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(device.get(key, "")) for key in ("FriendlyName", "InstanceId", "Class"))
    lower = text.lower()
    matched_keywords = [keyword for keyword in KNOWN_PROBE_KEYWORDS if keyword in lower]
    matched_usb_ids = [label for usb_id, label in KNOWN_PROBE_USB_IDS.items() if usb_id in lower]
    return {
        "matched": bool(matched_keywords or matched_usb_ids),
        "matched_keywords": matched_keywords,
        "matched_usb_ids": matched_usb_ids,
        "friendly_name": device.get("FriendlyName"),
        "instance_id": device.get("InstanceId"),
        "class": device.get("Class"),
        "status": device.get("Status"),
    }


def _recommendations(probes: list[dict[str, Any]]) -> list[str]:
    if probes:
        return ["Debug probe detected. If OpenOCD still fails, check interface config, target power, and probe driver."]
    return [
        "No known debug probe detected in present USB/PnP devices.",
        "Connect ST-Link/J-Link/CMSIS-DAP over USB and confirm it appears in Device Manager.",
        "If the probe is visible in Device Manager but not detected here, add its name to KNOWN_PROBE_KEYWORDS.",
    ]
