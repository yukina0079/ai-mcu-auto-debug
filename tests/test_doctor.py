from __future__ import annotations

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
