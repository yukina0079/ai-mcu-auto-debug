from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.connection_diagnostics import run_openocd_connection_matrix
from ai_mcu_debug.models import DebugTargetConfig


def _target(tmp_path: Path) -> DebugTargetConfig:
    return DebugTargetConfig(
        backend="openocd-gdb",
        cwd=tmp_path,
        server_command=[
            "openocd",
            "-f",
            "interface/cmsis-dap.cfg",
            "-c",
            "transport select swd",
            "-f",
            "target/stm32f1x.cfg",
            "-c",
            "adapter speed 100",
        ],
    )


def test_connection_matrix_records_safe_swd_attach_failures(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], cwd: Path, timeout_s: float) -> dict[str, object]:
        commands.append(command)
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "Info : CMSIS-DAP: Interface ready\nError: Error connecting DP: cannot read IDR\n",
        }

    report = run_openocd_connection_matrix(_target(tmp_path), tmp_path, runner=runner)

    assert report["ok"] is False
    assert report["status"] == "all_variants_failed"
    assert len(report["attempts"]) == 5
    assert any("adapter speed 10" in " ".join(command) for command in commands)
    assert any("connect_assert_srst" in " ".join(command) for command in commands)
    assert "swd_target_dp_not_responding" in report["attempts"][0]["failure_analysis"]["probable_causes"]
    assert (tmp_path / "connection_diagnostics.json").exists()


def test_connection_matrix_stops_when_variant_connects(tmp_path: Path) -> None:
    calls = 0

    def runner(command: list[str], cwd: Path, timeout_s: float) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"returncode": 1, "stdout": "", "stderr": "Error: Error connecting DP: cannot read IDR"}
        return {"returncode": 0, "stdout": "Info : stm32f1x.cpu: hardware has 6 breakpoints\nshutdown command invoked", "stderr": ""}

    report = run_openocd_connection_matrix(_target(tmp_path), tmp_path, runner=runner)

    assert report["ok"] is True
    assert report["status"] == "connection_variant_succeeded"
    assert len(report["attempts"]) == 2
    assert report["attempts"][1]["name"] == "swd_50khz"
