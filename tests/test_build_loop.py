from __future__ import annotations

import json
import sys
from pathlib import Path

from ai_mcu_debug.build import CMakeBuildAdapter, CommandBuildAdapter
from ai_mcu_debug.interfaces import BuildAdapter, RepairAdapter
from ai_mcu_debug.models import BuildConfig, BuildResult, RepairResult, RuntimeLogResult, SmokeTestResult
from ai_mcu_debug.repair.command import CommandRepairAdapter
from ai_mcu_debug.runner import BuildRepairSession, ClosedLoopSession


class FailingThenPassingBuild(BuildAdapter):
    def __init__(self) -> None:
        self.builds = 0

    def build(self) -> BuildResult:
        self.builds += 1
        if self.builds == 1:
            return BuildResult(False, ["build"], "", "main.c:1: error: nope", 1, ["main.c:1: error: nope"])
        return BuildResult(True, ["build"], "ok", "", 0)

    def flash(self) -> BuildResult:
        return BuildResult(True, ["flash"], "ok", "", 0)

    def smoke_test(self) -> SmokeTestResult:
        return SmokeTestResult(True, ["test"], "ok", "", 0)

    def collect_runtime_log(self) -> RuntimeLogResult:
        return RuntimeLogResult(True, ["runtime-log"], "uart ok", "", 0, "command", ["uart ok"])


class RecordingRepair(RepairAdapter):
    def __init__(self) -> None:
        self.repairs = 0

    def repair_build(self, result: BuildResult, attempt: int) -> RepairResult:
        self.repairs += 1
        assert result.errors == ["main.c:1: error: nope"]
        assert attempt == 1
        return RepairResult(True, ["ai-repair"], "fixed", "", 0)


def test_build_repair_session_rebuilds_after_repair() -> None:
    build = FailingThenPassingBuild()
    repair = RecordingRepair()

    report = BuildRepairSession(build, repair, max_iterations=3).run()

    assert report["ok"] is True
    assert build.builds == 2
    assert repair.repairs == 1


def test_cmake_adapter_runs_smoke_test_command(tmp_path: Path) -> None:
    adapter = CMakeBuildAdapter(
        BuildConfig(
            backend="cmake",
            source_dir=tmp_path,
            smoke_test_command=[sys.executable, "-c", "print('smoke ok')"],
        )
    )

    result = adapter.smoke_test()

    assert result.ok is True
    assert "smoke ok" in result.stdout


def test_command_adapter_runs_build_command(tmp_path: Path) -> None:
    adapter = CommandBuildAdapter(
        BuildConfig(
            backend="command",
            source_dir=tmp_path,
            build_command=[sys.executable, "-c", "print('generic build ok')"],
        )
    )

    result = adapter.build()

    assert result.ok is True
    assert "generic build ok" in result.stdout


def test_cmake_adapter_runs_runtime_log_command(tmp_path: Path) -> None:
    adapter = CMakeBuildAdapter(
        BuildConfig(
            backend="cmake",
            source_dir=tmp_path,
            runtime_log_command=[sys.executable, "-c", "print('uart ready')"],
        )
    )

    result = adapter.collect_runtime_log()

    assert result.ok is True
    assert result.source == "command"
    assert result.observations == ["uart ready"]


def test_cmake_adapter_audits_missing_command(tmp_path: Path, monkeypatch) -> None:
    audit_log = tmp_path / "audit_events.jsonl"
    monkeypatch.setenv("AI_MCU_DEBUG_AUDIT_LOG", str(audit_log))
    adapter = CMakeBuildAdapter(
        BuildConfig(
            backend="cmake",
            source_dir=tmp_path,
            build_command=["definitely-missing-command-for-ai-mcu-debug"],
        )
    )

    result = adapter.build()

    assert result.ok is False
    records = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "build_command"
    assert records[0]["ok"] is False


def test_repair_adapter_audits_missing_command(tmp_path: Path, monkeypatch) -> None:
    audit_log = tmp_path / "audit_events.jsonl"
    monkeypatch.setenv("AI_MCU_DEBUG_AUDIT_LOG", str(audit_log))
    adapter = CommandRepairAdapter(["definitely-missing-repair-command"], cwd=tmp_path)

    result = adapter.repair_build(BuildResult(False, ["build"], "", "error", 1, ["error"]), attempt=1)

    assert result.ok is False
    records = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "repair_command"
    assert records[0]["ok"] is False


def test_closed_loop_runs_build_flash_and_smoke() -> None:
    build = FailingThenPassingBuild()
    repair = RecordingRepair()

    report = ClosedLoopSession(build, repair, max_repair_iterations=3).run()

    assert report["ok"] is True
    assert report["build_repair"]["ok"] is True
    assert report["flash"]["ok"] is True
    assert report["smoke_test"]["ok"] is True
