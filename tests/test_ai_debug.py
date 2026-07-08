from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.build.cmake import CMakeBuildAdapter
from ai_mcu_debug.interfaces import BuildAdapter
from ai_mcu_debug.knowledge import build_mcu_context
from ai_mcu_debug.models import BuildConfig, BuildResult, DebugTask, RepairResult, RuntimeLogResult, SmokeTestResult
from ai_mcu_debug.runner.ai_debug import AiDebugSession
from tests.test_debug_session import FakeDebugAdapter


ROOT = Path(__file__).resolve().parents[1]
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = ROOT / "examples/firmware/stm32f103_blinky/linker.stm32f103rct6.ld"
STARTUP = ROOT / "examples/firmware/stm32f103_blinky/src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


class FakeBuildAdapter(BuildAdapter):
    def __init__(
        self,
        build_ok: bool = True,
        flash_ok: bool = True,
        smoke_ok: bool = True,
        runtime_ok: bool = True,
    ) -> None:
        self.calls: list[str] = []
        self.build_ok = build_ok
        self.flash_ok = flash_ok
        self.smoke_ok = smoke_ok
        self.runtime_ok = runtime_ok

    def build(self) -> BuildResult:
        self.calls.append("build")
        return BuildResult(ok=self.build_ok, command=["build"], stdout="", stderr="", returncode=0 if self.build_ok else 1)

    def flash(self) -> BuildResult:
        self.calls.append("flash")
        return BuildResult(ok=self.flash_ok, command=["flash"], stdout="", stderr="", returncode=0 if self.flash_ok else 1)

    def smoke_test(self) -> SmokeTestResult:
        self.calls.append("smoke")
        return SmokeTestResult(ok=self.smoke_ok, command=["smoke"], stdout="", stderr="", returncode=0 if self.smoke_ok else 1)

    def collect_runtime_log(self) -> RuntimeLogResult:
        self.calls.append("runtime-log")
        return RuntimeLogResult(
            ok=self.runtime_ok,
            command=["runtime-log"],
            stdout="uart: ready\n" if self.runtime_ok else "",
            stderr="" if self.runtime_ok else "uart timeout",
            returncode=0 if self.runtime_ok else 1,
            source="command",
            observations=["uart: ready"] if self.runtime_ok else ["uart timeout"],
        )


class FakeRepairAdapter:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.inputs: list[BuildResult] = []

    def repair_build(self, result: BuildResult, attempt: int) -> RepairResult:
        self.calls.append(attempt)
        self.inputs.append(result)
        return RepairResult(ok=True, command=["repair"], stdout="fixed", stderr="", returncode=0)


class FailingSwdAdapter(FakeDebugAdapter):
    def connect(self) -> None:
        self.calls.append("connect")
        raise RuntimeError("Could not connect")

    def diagnostics(self) -> dict[str, object]:
        return {
            "server_output_tail": [
                "Info : CMSIS-DAP: Interface ready",
                "Error: Error connecting DP: cannot read IDR",
            ]
        }


def _context(path: Path) -> Path:
    build_mcu_context(
        chip="STM32F103RCT6",
        svd_path=SVD,
        output_path=path,
        linker_path=LINKER,
        startup_path=STARTUP,
        documents=[("datasheet", DATASHEET), ("errata", ERRATA)],
        board="test",
        package_name="LQFP64",
    )
    return path


def test_ai_debug_dry_run_builds_and_never_flashes(tmp_path: Path) -> None:
    build = FakeBuildAdapter()
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="dry-run",
        build_adapter=build,
        report_dir=tmp_path,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert build.calls == ["build", "smoke", "runtime-log"]
    assert report["runtime_log"]["observations"] == ["uart: ready"]
    assert set(report["safety"]) == {
        "flash_allowed",
        "repair_allowed",
        "register_write_allowed",
        "memory_write_allowed",
        "force_allowed",
    }
    assert all({"name", "ok", "required", "skipped", "reason"} <= set(step) for step in report["steps"])
    assert (tmp_path / "ai_debug_report.json").exists()
    persisted = (tmp_path / "ai_debug_report.json").read_text(encoding="utf-8")
    assert "report_path" in persisted


def test_ai_debug_read_only_runs_acceptance_and_knowledge_analysis(tmp_path: Path) -> None:
    task = DebugTask(
        name="read_only",
        breakpoints=["main"],
        registers=["pc", "sp", "lr", "xpsr"],
        memory_reads=[(0x20000000, 4)],
        step_count=1,
    )
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="read-only",
        build_adapter=FakeBuildAdapter(),
        debug_adapter=FakeDebugAdapter(),
        debug_task=task,
        report_dir=tmp_path,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is True
    assert report["accept_first_stage"]["ok"] is True
    assert report["knowledge_analysis"]["ok"] is True
    assert (tmp_path / "read_only.knowledge.json").exists()


def test_ai_debug_run_mode_blocks_flash_without_explicit_policy(tmp_path: Path) -> None:
    build = FakeBuildAdapter()
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="run",
        build_adapter=build,
        report_dir=tmp_path,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is False
    assert report["status"] == "flash_blocked_by_policy"
    assert build.calls == ["build"]
    flash_step = next(step for step in report["steps"] if step["name"] == "flash")
    assert flash_step["skipped"] is True
    assert flash_step["reason"] == "flash_blocked_by_policy"


def test_ai_debug_run_mode_can_flash_smoke_debug_and_analyze_when_allowed(tmp_path: Path) -> None:
    build = FakeBuildAdapter()
    task = DebugTask(
        name="run_loop",
        breakpoints=["main"],
        registers=["pc", "sp", "lr", "xpsr"],
        memory_reads=[(0x20000000, 4)],
        step_count=1,
    )
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="run",
        build_adapter=build,
        debug_adapter=FakeDebugAdapter(),
        debug_task=task,
        report_dir=tmp_path,
        allow_flash=True,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert build.calls == ["build", "flash", "smoke", "runtime-log"]
    assert report["debug"]["ok"] is True
    assert report["knowledge_analysis"]["ok"] is True
    assert report["run_id"].startswith("run_")
    assert any(item["kind"] == "audit_log" for item in report["artifacts"])


def test_ai_debug_audit_events_include_run_and_step_ids(tmp_path: Path, monkeypatch) -> None:
    audit_log = tmp_path / "audit_events.jsonl"
    monkeypatch.setenv("AI_MCU_DEBUG_AUDIT_LOG", str(audit_log))
    build = CMakeBuildAdapter(
        BuildConfig(
            backend="cmake",
            source_dir=tmp_path,
            build_command=["python", "-c", "print('build')"],
            flash_command=["python", "-c", "print('flash')"],
            smoke_test_command=["python", "-c", "print('smoke')"],
            runtime_log_command=["python", "-c", "print('uart ready')"],
        )
    )
    task = DebugTask(name="trace", registers=["pc"])
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="run",
        build_adapter=build,
        debug_adapter=FakeDebugAdapter(),
        debug_task=task,
        report_dir=tmp_path,
        allow_flash=True,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    records = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert {record["run_id"] for record in records} == {report["run_id"]}
    assert {"flash", "runtime-log", "debug"} <= {record.get("step_id") for record in records}


def test_ai_debug_stops_before_smoke_or_flash_when_build_fails(tmp_path: Path) -> None:
    build = FakeBuildAdapter(build_ok=False)
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="run",
        build_adapter=build,
        report_dir=tmp_path,
        allow_flash=True,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is False
    assert report["status"] == "build_failed"
    assert build.calls == ["build"]


def test_ai_debug_run_mode_treats_runtime_log_as_required_evidence(tmp_path: Path) -> None:
    build = FakeBuildAdapter(runtime_ok=False)
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="run",
        build_adapter=build,
        report_dir=tmp_path,
        allow_flash=True,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is False
    assert report["status"] == "runtime_log_failed"
    assert build.calls == ["build", "flash", "smoke", "runtime-log"]


def test_ai_debug_can_trigger_post_runtime_repair_from_evidence(tmp_path: Path) -> None:
    build = FakeBuildAdapter(runtime_ok=False)
    repair = FakeRepairAdapter()
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="run",
        build_adapter=build,
        repair_adapter=repair,
        report_dir=tmp_path,
        allow_flash=True,
        allow_repair=True,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True},
    )

    report = session.run()

    assert report["ok"] is False
    assert report["post_runtime_repair"]["ok"] is True
    assert repair.calls == [4]
    assert repair.inputs[0].errors == ["runtime_log_failed: uart timeout"]


def test_ai_debug_includes_target_validation_warnings(tmp_path: Path) -> None:
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
    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="dry-run",
        build_adapter=FakeBuildAdapter(),
        target_config_path=target,
        report_dir=tmp_path,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {
            "ok": True,
            "probes": [{"matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"]}],
        },
    )

    report = session.run()

    assert report["ok"] is True
    assert report["target_validation"]["warnings"][0]["code"] == "probe_interface_mismatch"
    assert any("interface/stlink.cfg" in action for action in report["next_actions"])


def test_ai_debug_read_only_runs_connection_diagnostics_after_swd_attach_failure(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(
            {
                "backend": "openocd-gdb",
                "server_command": ["openocd", "-f", "interface/cmsis-dap.cfg", "-f", "target/stm32f1x.cfg"],
            }
        ),
        encoding="utf-8",
    )
    task = DebugTask(name="swd_fail", registers=["pc"])

    def diagnoser(target_config, report_dir, timeout_s):
        path = report_dir / "connection_diagnostics.json"
        path.write_text("{}", encoding="utf-8")
        return {
            "ok": False,
            "status": "all_variants_failed",
            "report_path": str(path),
            "next_actions": ["Check STM32 board seating and SWD wiring."],
        }

    session = AiDebugSession(
        project_path=ROOT,
        context_path=_context(tmp_path / "context.json"),
        mode="read-only",
        build_adapter=FakeBuildAdapter(),
        debug_adapter=FailingSwdAdapter(),
        debug_task=task,
        target_config_path=target,
        report_dir=tmp_path,
        doctor_runner=lambda: {"ok": True},
        probe_scanner=lambda: {"ok": True, "probes": [{"matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"]}]},
        connection_diagnoser=diagnoser,
    )

    report = session.run()

    assert report["ok"] is False
    assert report["status"] == "read_only_debug_failed"
    assert report["connection_diagnostics"]["status"] == "all_variants_failed"
    assert any(step["name"] == "connection-diagnose" for step in report["steps"])
    assert any(item["kind"] == "connection_diagnostics" for item in report["artifacts"])
    assert "Check STM32 board seating and SWD wiring." in report["next_actions"]
