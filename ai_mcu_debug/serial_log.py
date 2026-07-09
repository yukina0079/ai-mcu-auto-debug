from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def collect_serial_log(
    *,
    port: str,
    baud: int = 115200,
    duration_s: float = 5.0,
    timeout_s: float = 0.2,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Collect UART/USB-serial evidence with pyserial when it is installed."""

    if duration_s <= 0:
        return _finalize(
            {
                "ok": False,
                "status": "invalid_duration",
                "port": port,
                "baud": baud,
                "duration_s": duration_s,
                "next_actions": ["Use a positive --duration-s value."],
            },
            output,
        )

    try:
        import serial  # type: ignore[import-not-found]
    except ImportError:
        return _finalize(
            {
                "ok": False,
                "status": "pyserial_missing",
                "port": port,
                "baud": baud,
                "duration_s": duration_s,
                "next_actions": ["Install pyserial with: python -m pip install pyserial"],
            },
            output,
        )

    lines: list[str] = []
    bytes_read = 0
    started = time.monotonic()
    try:
        with serial.Serial(port=port, baudrate=baud, timeout=timeout_s) as stream:
            deadline = started + duration_s
            while time.monotonic() < deadline:
                chunk = stream.readline()
                if not chunk:
                    continue
                bytes_read += len(chunk)
                text = chunk.decode("utf-8", errors="replace").strip()
                if text:
                    lines.append(text)
    except Exception as exc:  # pyserial raises platform-specific subclasses.
        return _finalize(
            {
                "ok": False,
                "status": "serial_read_failed",
                "port": port,
                "baud": baud,
                "duration_s": duration_s,
                "error": str(exc),
                "lines": lines,
                "bytes_read": bytes_read,
                "observations": _observations(lines),
            },
            output,
        )

    return _finalize(
        {
            "ok": True,
            "status": "ok",
            "source": "serial",
            "port": port,
            "baud": baud,
            "duration_s": duration_s,
            "lines": lines,
            "bytes_read": bytes_read,
            "observations": _observations(lines),
        },
        output,
    )


def _observations(lines: list[str]) -> list[str]:
    observations: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        observations.append(stripped)
        if len(observations) >= 50:
            break
    return observations


def _finalize(report: dict[str, Any], output: str | Path | None) -> dict[str, Any]:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report["output"] = str(output_path)
    return report
