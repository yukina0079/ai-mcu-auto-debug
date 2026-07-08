from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from ai_mcu_debug.audit_log import audit_log_path, pop_audit_context, push_audit_context
from ai_mcu_debug.config import load_target_config
from ai_mcu_debug.connection_diagnostics import run_openocd_connection_matrix
from ai_mcu_debug.doctor import run_doctor
from ai_mcu_debug.interfaces import BuildAdapter, DebugAdapter, RepairAdapter
from ai_mcu_debug.knowledge import check_context, compare_debug_report, prepare_mcu
from ai_mcu_debug.models import BuildResult, DebugTargetConfig, DebugTask
from ai_mcu_debug.probe_scan import scan_debug_probes
from ai_mcu_debug.runner.acceptance import FirstPhaseAcceptance
from ai_mcu_debug.runner.build_loop import BuildRepairSession
from ai_mcu_debug.runner.debug_session import AutoDebugSession
from ai_mcu_debug.target_validation import validate_debug_target


class AiDebugSession:
    """Skill-friendly orchestration entry point.

    Modes:
    - dry-run: prepare/check context, inspect tools/probe, build and smoke test only.
    - read-only: dry-run plus first-stage debug acceptance; never flashes firmware.
    - run: explicitly authorized build/flash/smoke/debug loop.
    """

    def __init__(
        self,
        project_path: Path,
        context_path: Path,
        mode: str = "dry-run",
        prepare_options: dict[str, Any] | None = None,
        build_adapter: BuildAdapter | None = None,
        repair_adapter: RepairAdapter | None = None,
        debug_adapter: DebugAdapter | None = None,
        debug_task: DebugTask | None = None,
        target_config_path: Path | None = None,
        report_dir: Path = Path("debug_runs/ai_debug"),
        allow_flash: bool = False,
        allow_repair: bool = False,
        max_repair_iterations: int = 3,
        doctor_runner: Callable[[], dict[str, Any]] = run_doctor,
        probe_scanner: Callable[[], dict[str, Any]] = scan_debug_probes,
        connection_diagnoser: Callable[[DebugTargetConfig, Path, float], dict[str, Any]] = run_openocd_connection_matrix,
        connection_diagnostic_timeout_s: float = 12.0,
    ) -> None:
        self.project_path = project_path
        self.context_path = context_path
        self.mode = mode
        self.prepare_options = prepare_options or {}
        self.build_adapter = build_adapter
        self.repair_adapter = repair_adapter
        self.debug_adapter = debug_adapter
        self.debug_task = debug_task
        self.target_config_path = target_config_path
        self.report_dir = report_dir
        self.allow_flash = allow_flash
        self.allow_repair = allow_repair
        self.max_repair_iterations = max_repair_iterations
        self.doctor_runner = doctor_runner
        self.probe_scanner = probe_scanner
        self.connection_diagnoser = connection_diagnoser
        self.connection_diagnostic_timeout_s = connection_diagnostic_timeout_s

    def run(self) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        report: dict[str, Any] = {
            "ok": False,
            "mode": self.mode,
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "project": str(self.project_path),
            "context": str(self.context_path),
            "safety": {
                "flash_allowed": self.allow_flash,
                "repair_allowed": self.allow_repair,
                "register_write_allowed": False,
                "memory_write_allowed": False,
                "force_allowed": False,
            },
            "steps": [],
            "artifacts": [],
            "uncertain": [],
            "next_actions": [],
        }
        token = push_audit_context(run_id=run_id, tool="ai-debug", mode=self.mode, report_dir=str(self.report_dir))
        try:
            if self.mode not in {"dry-run", "read-only", "run"}:
                report["status"] = "unsupported_mode"
                report["next_actions"] = ["Use --mode dry-run, --mode read-only, or --mode run."]
                return self._finish(report)

            with _audit_step("prepare-context"):
                context_ok = self._prepare_or_check_context(report)
            report["doctor"] = self.doctor_runner()
            self._add_step(report, "doctor", bool(report["doctor"].get("ok")), required=True)
            report["probe_scan"] = self.probe_scanner()
            self._add_step(report, "probe-scan", bool(report["probe_scan"].get("ok")), required=False)
            self._validate_target(report)

            build_ok = self._run_build(report)

            if self.mode == "read-only":
                self._run_read_only_debug(report)
            elif self.mode == "run":
                self._run_authorized_loop(report, context_ok=context_ok, build_ok=build_ok)

            report["status"] = self._status(report)
            report["ok"] = not self._has_required_failure(report)
            return self._finish(report)
        finally:
            pop_audit_context(token)

    def _prepare_or_check_context(self, report: dict[str, Any]) -> bool:
        if self.context_path.exists():
            context_check = check_context(self.context_path)
            report["context_check"] = context_check
            self._add_step(report, "check-context", bool(context_check.get("ok")), required=True)
            if self.context_path.exists():
                self._add_artifact(report, "mcu_context", self.context_path)
            return bool(context_check.get("ok"))
        prepare = prepare_mcu(
            project_path=self.project_path,
            output_path=self.context_path,
            **self.prepare_options,
        )
        report["prepare_mcu"] = prepare
        self._add_step(report, "prepare-mcu", bool(prepare.get("ok")), required=True, reason=prepare.get("status"))
        if self.context_path.exists():
            context_check = check_context(self.context_path)
            report["context_check"] = context_check
            self._add_step(report, "check-context", bool(context_check.get("ok")), required=True)
            self._add_artifact(report, "mcu_context", self.context_path)
            return bool(context_check.get("ok"))
        return False

    def _validate_target(self, report: dict[str, Any]) -> None:
        if not self.target_config_path:
            self._add_step(report, "validate-target", None, required=False, skipped=True, reason="target_config_missing")
            return
        validation = validate_debug_target(self.target_config_path, probe_report=report.get("probe_scan"))
        report["target_validation"] = validation
        self._add_step(report, "validate-target", bool(validation.get("ok")), required=True)
        for warning in validation.get("warnings", []):
            action = warning.get("message")
            if action and action not in report["next_actions"]:
                report["next_actions"].append(action)

    def _run_build(self, report: dict[str, Any]) -> bool | None:
        build_required = self.mode == "run"
        if not self.build_adapter:
            self._add_step(report, "build", None, required=build_required, skipped=True, reason="build_config_missing")
            if build_required:
                report["next_actions"].append("Provide --build-config so the run loop can build firmware.")
            return None
        if self.mode == "run" and self.allow_repair and self.repair_adapter:
            with _audit_step("build-repair"):
                build_report = BuildRepairSession(
                    self.build_adapter,
                    self.repair_adapter,
                    self.max_repair_iterations,
                ).run()
            report["build_repair"] = build_report
            self._add_step(report, "build-repair", bool(build_report.get("ok")), required=True)
            return bool(build_report.get("ok"))
        with _audit_step("build"):
            build = self.build_adapter.build()
        report["build"] = asdict(build)
        self._add_step(report, "build", build.ok, required=True)
        if not build.ok:
            if self.mode == "run" and not self.allow_repair:
                report["next_actions"].append("Build failed. Re-run with --allow-repair only if code edits by the configured repair tool are acceptable.")
            return False
        if self.mode != "run":
            with _audit_step("smoke-test"):
                smoke = self.build_adapter.smoke_test()
            report["smoke_test"] = asdict(smoke)
            self._add_step(report, "smoke-test", smoke.ok, required=True)
            self._run_runtime_log(report, required=False)
            return smoke.ok
        return True

    def _run_read_only_debug(self, report: dict[str, Any]) -> None:
        if not self.debug_adapter or not self.debug_task:
            self._add_step(
                report,
                "accept-first-stage",
                None,
                required=False,
                skipped=True,
                reason="debug_target_or_task_missing",
            )
            report["next_actions"].append("Provide --target and --task to run first-stage read-only hardware acceptance.")
            return
        with _audit_step("accept-first-stage"):
            acceptance = FirstPhaseAcceptance(self.debug_adapter, self.report_dir).run(self.debug_task)
        report["accept_first_stage"] = acceptance
        self._add_step(report, "accept-first-stage", bool(acceptance.get("ok")), required=True)
        if not acceptance.get("ok"):
            self._merge_debug_failure(report, acceptance.get("debug_report", {}))
            self._run_connection_diagnostics_if_useful(report, acceptance.get("debug_report", {}))
        debug_report_path = self.report_dir / f"{self.debug_task.name}.json"
        if debug_report_path.exists():
            self._add_artifact(report, "debug_report", debug_report_path)
        if self.context_path.exists() and debug_report_path.exists():
            knowledge_output = self.report_dir / f"{self.debug_task.name}.knowledge.json"
            knowledge = compare_debug_report(self.context_path, debug_report_path, knowledge_output)
            report["knowledge_analysis"] = knowledge
            self._add_step(report, "analyze-debug-report", bool(knowledge.get("ok")), required=True)
            self._add_artifact(report, "knowledge_report", knowledge_output)
            self._run_evidence_repair_if_needed(report, knowledge)

    def _run_authorized_loop(self, report: dict[str, Any], context_ok: bool, build_ok: bool | None) -> None:
        if not context_ok:
            self._add_step(report, "flash", False, required=True, skipped=True, reason="context_incomplete")
            report["next_actions"].append("Complete mcu_context before flashing or running a hardware debug loop.")
            return
        if build_ok is not True:
            self._add_step(report, "flash", None, required=True, skipped=True, reason="build_not_ok")
            return
        if not self.build_adapter:
            self._add_step(report, "flash", None, required=True, skipped=True, reason="build_adapter_missing")
            return
        if not self.allow_flash:
            self._add_step(report, "flash", False, required=True, skipped=True, reason="flash_blocked_by_policy")
            report["next_actions"].append("Re-run with --allow-flash only after confirming the target board may be programmed.")
            return

        with _audit_step("flash"):
            flash = self.build_adapter.flash()
        report["flash"] = asdict(flash)
        self._add_step(report, "flash", flash.ok, required=True)
        if not flash.ok:
            return

        with _audit_step("smoke-test"):
            smoke = self.build_adapter.smoke_test()
        report["smoke_test"] = asdict(smoke)
        self._add_step(report, "smoke-test", smoke.ok, required=True)
        if not smoke.ok:
            return
        runtime_ok = self._run_runtime_log(report, required=True)
        if runtime_ok is False:
            self._run_runtime_repair_if_needed(report)
            return

        if not self.debug_adapter or not self.debug_task:
            self._add_step(report, "debug", None, required=False, skipped=True, reason="debug_target_or_task_missing")
            report["next_actions"].append("Provide --target and --task to include hardware debug evidence in the run loop.")
            return

        with _audit_step("debug"):
            debug_report = AutoDebugSession(self.debug_adapter, self.report_dir).run(self.debug_task)
        report["debug"] = debug_report
        self._add_step(report, "debug", bool(debug_report.get("ok")), required=True)
        if not debug_report.get("ok"):
            self._merge_debug_failure(report, debug_report)
            self._run_connection_diagnostics_if_useful(report, debug_report)
        debug_report_path = self.report_dir / f"{self.debug_task.name}.json"
        if debug_report_path.exists():
            self._add_artifact(report, "debug_report", debug_report_path)
        if self.context_path.exists() and debug_report_path.exists():
            knowledge_output = self.report_dir / f"{self.debug_task.name}.knowledge.json"
            knowledge = compare_debug_report(self.context_path, debug_report_path, knowledge_output)
            report["knowledge_analysis"] = knowledge
            self._add_step(report, "analyze-debug-report", bool(knowledge.get("ok")), required=True)
            self._add_artifact(report, "knowledge_report", knowledge_output)
            self._run_evidence_repair_if_needed(report, knowledge)

    def _finish(self, report: dict[str, Any]) -> dict[str, Any]:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._add_artifact(report, "audit_log", audit_log_path())
        path = self.report_dir / "ai_debug_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._add_artifact(report, "ai_debug_report", path)
        report["report_path"] = str(path)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return report

    def _run_runtime_log(self, report: dict[str, Any], required: bool) -> bool | None:
        if not self.build_adapter:
            self._add_step(report, "runtime-log", None, required=required, skipped=True, reason="build_config_missing")
            return None
        with _audit_step("runtime-log"):
            runtime_log = self.build_adapter.collect_runtime_log()
        report["runtime_log"] = asdict(runtime_log)
        self._add_step(report, "runtime-log", runtime_log.ok, required=required, reason=runtime_log.source)
        if runtime_log.observations:
            report.setdefault("runtime_observations", []).extend(runtime_log.observations)
        return runtime_log.ok

    def _run_evidence_repair_if_needed(self, report: dict[str, Any], knowledge: dict[str, Any]) -> None:
        if not self.allow_repair or not self.repair_adapter:
            self._add_step(
                report,
                "post-debug-repair",
                None,
                required=False,
                skipped=True,
                reason="repair_not_allowed_or_not_configured",
            )
            return
        if knowledge.get("ok") and report.get("debug", {}).get("ok") and report.get("runtime_log", {}).get("ok", True):
            self._add_step(report, "post-debug-repair", None, required=False, skipped=True, reason="no_evidence_failure")
            return
        if _has_physical_debug_failure(report):
            self._add_step(report, "post-debug-repair", None, required=False, skipped=True, reason="physical_or_probe_failure")
            report["next_actions"].append("Fix probe, SWD, reset, or power evidence before allowing code repair.")
            return
        synthetic_build = _evidence_repair_build_result(report)
        with _audit_step("post-debug-repair"):
            repair = self.repair_adapter.repair_build(synthetic_build, self.max_repair_iterations + 1)
        report["post_debug_repair"] = asdict(repair)
        self._add_step(report, "post-debug-repair", repair.ok, required=False)

    def _run_runtime_repair_if_needed(self, report: dict[str, Any]) -> None:
        if not self.allow_repair or not self.repair_adapter:
            self._add_step(
                report,
                "post-runtime-repair",
                None,
                required=False,
                skipped=True,
                reason="repair_not_allowed_or_not_configured",
            )
            return
        synthetic_build = _evidence_repair_build_result(report)
        with _audit_step("post-runtime-repair"):
            repair = self.repair_adapter.repair_build(synthetic_build, self.max_repair_iterations + 1)
        report["post_runtime_repair"] = asdict(repair)
        self._add_step(report, "post-runtime-repair", repair.ok, required=False)

    @staticmethod
    def _add_step(
        report: dict[str, Any],
        name: str,
        ok: bool | None,
        required: bool,
        skipped: bool = False,
        reason: object | None = None,
    ) -> None:
        report["steps"].append(
            {
                "name": name,
                "ok": ok,
                "required": required,
                "skipped": skipped,
                "reason": reason,
            }
        )

    @staticmethod
    def _add_artifact(report: dict[str, Any], kind: str, path: Path) -> None:
        item = {"kind": kind, "path": str(path)}
        if item not in report["artifacts"]:
            report["artifacts"].append(item)

    @staticmethod
    def _has_required_failure(report: dict[str, Any]) -> bool:
        return any(step["required"] and step.get("ok") is not True for step in report["steps"])

    def _status(self, report: dict[str, Any]) -> str:
        if self._step_failed(report, "prepare-mcu"):
            prepare_status = report.get("prepare_mcu", {}).get("status")
            return str(prepare_status or "missing_required_document")
        if self._step_failed(report, "check-context"):
            return "context_incomplete"
        if self._step_failed(report, "doctor"):
            return "doctor_failed"
        if self._step_failed(report, "validate-target"):
            return "target_validation_failed"
        if self._step_failed(report, "build") or self._step_failed(report, "build-repair"):
            return "build_failed"
        if self._step_failed(report, "flash"):
            reason = self._step_reason(report, "flash")
            return str(reason or "flash_failed")
        if self._step_failed(report, "smoke-test"):
            return "smoke_test_failed"
        if self._step_failed(report, "runtime-log"):
            return "runtime_log_failed"
        if self._step_failed(report, "accept-first-stage"):
            return "read_only_debug_failed"
        if self._step_failed(report, "debug"):
            return "debug_failed"
        if self._step_failed(report, "analyze-debug-report"):
            return "knowledge_analysis_failed"
        return "ok"

    @staticmethod
    def _step_failed(report: dict[str, Any], name: str) -> bool:
        return any(step["name"] == name and step["required"] and step.get("ok") is not True for step in report["steps"])

    @staticmethod
    def _step_reason(report: dict[str, Any], name: str) -> object | None:
        for step in report["steps"]:
            if step["name"] == name:
                return step.get("reason")
        return None

    @staticmethod
    def _merge_debug_failure(report: dict[str, Any], debug_report: dict[str, Any]) -> None:
        failure = debug_report.get("failure_analysis") or {}
        for action in failure.get("next_actions", []):
            if action not in report["next_actions"]:
                report["next_actions"].append(action)
        for cause in failure.get("probable_causes", []):
            item = {"kind": "debug_failure_cause", "value": cause}
            if item not in report["uncertain"]:
                report["uncertain"].append(item)

    def _run_connection_diagnostics_if_useful(self, report: dict[str, Any], debug_report: dict[str, Any]) -> None:
        failure = debug_report.get("failure_analysis") or {}
        causes = set(failure.get("probable_causes", []))
        if "swd_target_dp_not_responding" not in causes and "target_reset_line_held_low" not in causes:
            self._add_step(
                report,
                "connection-diagnose",
                None,
                required=False,
                skipped=True,
                reason="failure_not_swd_attach_related",
            )
            return
        if not self.target_config_path:
            self._add_step(
                report,
                "connection-diagnose",
                None,
                required=False,
                skipped=True,
                reason="target_config_missing",
            )
            return
        try:
            target = load_target_config(self.target_config_path)
            diagnostics = self.connection_diagnoser(target, self.report_dir, self.connection_diagnostic_timeout_s)
        except Exception as exc:
            diagnostics = {
                "ok": False,
                "status": "connection_diagnostics_failed",
                "error": str(exc),
                "next_actions": ["Inspect target config and rerun connection-diagnose manually."],
            }
        report["connection_diagnostics"] = diagnostics
        self._add_step(report, "connection-diagnose", bool(diagnostics.get("ok")), required=False, reason=diagnostics.get("status"))
        path = diagnostics.get("report_path")
        if path:
            self._add_artifact(report, "connection_diagnostics", Path(str(path)))
        for action in diagnostics.get("next_actions", []):
            if action not in report["next_actions"]:
                report["next_actions"].append(action)


def _has_physical_debug_failure(report: dict[str, Any]) -> bool:
    causes: set[str] = set()
    failure = report.get("debug", {}).get("failure_analysis", {})
    causes.update(str(cause) for cause in failure.get("probable_causes", []))
    for item in report.get("uncertain", []):
        if item.get("kind") == "debug_failure_cause":
            causes.add(str(item.get("value")))
    physical_causes = {
        "debug_probe_not_found",
        "swd_target_dp_not_responding",
        "target_reset_line_held_low",
        "openocd_target_config_or_wiring",
    }
    return bool(causes & physical_causes)


def _evidence_repair_build_result(report: dict[str, Any]) -> BuildResult:
    evidence = {
        "status": report.get("status"),
        "debug": report.get("debug"),
        "knowledge_analysis": report.get("knowledge_analysis"),
        "runtime_log": report.get("runtime_log"),
        "next_actions": report.get("next_actions", []),
    }
    return BuildResult(
        ok=False,
        command=["ai-debug-evidence-repair"],
        stdout=json.dumps(evidence, ensure_ascii=False, default=str),
        stderr="debug_or_runtime_evidence_failed",
        returncode=1,
        errors=_evidence_errors(report),
        warnings=[],
        artifacts={},
    )


def _evidence_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    debug = report.get("debug", {})
    if debug and not debug.get("ok", False):
        errors.append(f"debug_failed: {debug.get('error') or debug.get('conclusions')}")
    knowledge = report.get("knowledge_analysis", {})
    if knowledge and not knowledge.get("ok", False):
        errors.append(f"knowledge_analysis_failed: {knowledge.get('status') or knowledge.get('failures')}")
    runtime = report.get("runtime_log", {})
    if runtime and not runtime.get("ok", True):
        errors.append(f"runtime_log_failed: {runtime.get('stderr') or runtime.get('stdout')}")
    return errors or ["evidence_failed"]


@contextmanager
def _audit_step(step_id: str) -> Iterator[None]:
    token = push_audit_context(step_id=step_id)
    try:
        yield
    finally:
        pop_audit_context(token)
