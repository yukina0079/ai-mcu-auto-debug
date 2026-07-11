from __future__ import annotations

import json

from ai_mcu_debug import doctor


def test_doctor_reports_ok_when_gdb_and_backend_exist(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        return f"C:/tools/{name}.exe" if name in {"arm-none-eabi-gdb", "openocd", "cmake", "pytest"} else None

    monkeypatch.setattr(doctor.shutil, "which", fake_which)
    monkeypatch.setattr(doctor, "_read_version", lambda path: "tool version")

    report = doctor.run_doctor()

    assert report["ok"] is True
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["target_gdb"]["available"] is True
    assert checks["openocd"]["available"] is True
    assert report["recommendations"] == ["Toolchain looks ready for first-stage hardware acceptance."]


def test_doctor_can_gate_probe_rs_debug_backend(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        return f"C:/tools/{name}.exe" if name in {"arm-none-eabi-gdb", "probe-rs", "pytest"} else None

    monkeypatch.setattr(doctor.shutil, "which", fake_which)
    monkeypatch.setattr(doctor, "_read_version", lambda path: "tool version")

    report = doctor.run_doctor(debug_backend="probe-rs-gdb", build_backend="command")

    assert report["ok"] is True
    gates = {item["name"]: item for item in report["readiness_gates"]}
    assert gates["target_gdb"]["ok"] is True
    assert gates["probe_rs"]["ok"] is True


def test_doctor_can_gate_platformio_build_backend(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        return f"C:/tools/{name}.exe" if name in {"arm-none-eabi-gdb", "openocd", "pio", "pytest"} else None

    monkeypatch.setattr(doctor.shutil, "which", fake_which)
    monkeypatch.setattr(doctor, "_read_version", lambda path: "tool version")

    report = doctor.run_doctor(debug_backend="openocd-gdb", build_backend="platformio")

    assert report["ok"] is True
    gates = {item["name"]: item for item in report["readiness_gates"]}
    assert gates["openocd"]["ok"] is True
    assert gates["platformio"]["ok"] is True


def test_discover_esp_idf_from_eim_config(tmp_path) -> None:
    idf_path = tmp_path / "esp-idf"
    tools_path = tmp_path / "tools"
    python = tools_path / "python" / "venv" / "Scripts" / "python.exe"
    activation = tools_path / "PowerShell_profile.ps1"
    idf_py = idf_path / "tools" / "idf.py"
    gdb = tools_path / "riscv32-esp-elf-gdb" / "v1" / "bin" / "riscv32-esp-elf-gdb.exe"
    openocd = tools_path / "openocd-esp32" / "v1" / "bin" / "openocd.exe"
    scripts = tools_path / "openocd-esp32" / "v1" / "share" / "openocd" / "scripts"
    for path in (python, activation, idf_py, gdb, openocd):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    scripts.mkdir(parents=True)
    config = tools_path / "eim_idf.json"
    config.write_text(
        json.dumps(
            {
                "idfSelectedId": "selected",
                "idfInstalled": [
                    {
                        "id": "selected",
                        "name": "v6.0.2",
                        "path": str(idf_path),
                        "idfToolsPath": str(tools_path),
                        "python": str(python),
                        "activationScript": str(activation),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = doctor.discover_esp_idf(config)

    assert report["ok"] is True
    assert report["version"] == "v6.0.2"
    assert report["riscv_gdb"] == str(gdb)
    assert report["openocd"] == str(openocd)
    assert report["openocd_scripts"] == str(scripts)
