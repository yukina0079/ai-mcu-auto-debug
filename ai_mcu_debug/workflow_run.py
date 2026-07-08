from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ai_mcu_debug.workflow_plan import plan_workflow


ToolExecutor = Callable[[dict[str, Any]], dict[str, Any]]


def run_workflow(
    *,
    project_path: Path = Path("."),
    context_path: Path = Path("examples/mcu_context.json"),
    workspace_config: Path = Path(".embeddedskills/config.json"),
    report_dir: Path = Path("debug_runs/workflow_run"),
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
    max_steps: int = 8,
    allow_file_writes: bool = True,
    allow_hardware: bool = True,
    stop_on_failure: bool = True,
    executor: ToolExecutor | None = None,
) -> dict[str, Any]:
    """Execute safe workflow-plan recommendations until ready, blocked, or capped.

    This is the thin deterministic bridge between the read-only planner and the
    lower-level API tools. It never enables flash, repair, force, vision, or web
    search by itself; those remain explicit policy gates on the target tools.
    """

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "workflow_run_report.json"
    report: dict[str, Any] = {
        "ok": False,
        "status": "started",
        "started_at": _now(),
        "project": str(project_path),
        "context": str(context_path),
        "workspace_config": str(workspace_config),
        "report_dir": str(report_dir),
        "policy": {
            "max_steps": max_steps,
            "allow_file_writes": allow_file_writes,
            "allow_hardware": allow_hardware,
            "stop_on_failure": stop_on_failure,
            "flash_allowed": False,
            "repair_allowed": False,
            "force_allowed": False,
            "vision_allowed": False,
            "web_search_allowed": False,
        },
        "iterations": [],
        "executed_tool_calls": [],
        "skipped_tool_calls": [],
        "user_requests": [],
        "artifacts": [{"kind": "workflow_run_report", "path": str(report_path)}],
        "next_actions": [],
    }
    if max_steps < 1:
        report["status"] = "invalid_max_steps"
        report["next_actions"] = ["Use max_steps >= 1."]
        return _finish(report, report_path)

    execute_tool = executor or _execute_tool_call
    for index in range(max_steps):
        plan = plan_workflow(
            project_path=project_path,
            context_path=context_path,
            workspace_config=workspace_config,
            chip=chip,
            svd_path=svd_path,
            linker_path=linker_path,
            startup_path=startup_path,
            extra_docs=extra_docs or [],
            doc_repo_paths=doc_repo_paths or [],
        )
        iteration = {
            "index": index + 1,
            "plan_status": plan.get("status"),
            "plan_ok": plan.get("ok"),
            "recommended_tool_count": len(plan.get("recommended_tool_calls", [])),
            "user_request_count": len(plan.get("user_requests", [])),
        }
        report["iterations"].append(iteration)

        if plan.get("user_requests"):
            report["status"] = str(plan.get("status") or "awaiting_user_input")
            report["user_requests"] = list(plan.get("user_requests", []))
            report["next_actions"] = list(plan.get("next_actions", []))
            return _finish(report, report_path)

        calls = list(plan.get("recommended_tool_calls", []))
        if not calls:
            report["ok"] = bool(plan.get("ok"))
            report["status"] = str(plan.get("status") or ("ok" if report["ok"] else "no_recommendations"))
            report["next_actions"] = list(plan.get("next_actions", []))
            return _finish(report, report_path)

        blocked = False
        failed = False
        for call in calls:
            decision = _execution_decision(
                call,
                allow_file_writes=allow_file_writes,
                allow_hardware=allow_hardware,
            )
            if not decision["execute"]:
                skipped = {
                    "tool": call.get("tool"),
                    "arguments": call.get("arguments", {}),
                    "cli": call.get("cli"),
                    "decision": decision,
                }
                report["skipped_tool_calls"].append(skipped)
                blocked = True
                if stop_on_failure:
                    break
                continue

            try:
                result = execute_tool(call)
            except Exception as exc:
                result = {
                    "ok": False,
                    "status": "tool_call_exception",
                    "tool": call.get("tool"),
                    "error": str(exc),
                    "next_actions": ["Inspect the failing tool arguments and rerun workflow-plan before retrying."],
                }
            execution = {
                "tool": call.get("tool"),
                "arguments": call.get("arguments", {}),
                "cli": call.get("cli"),
                "safety": call.get("safety", {}),
                "ok": bool(result.get("ok")),
                "status": result.get("status") or ("ok" if result.get("ok") else "failed"),
                "result": result,
            }
            report["executed_tool_calls"].append(execution)
            _collect_artifacts(report, result)
            if not result.get("ok"):
                failed = True
                if stop_on_failure:
                    break

        if failed:
            last = report["executed_tool_calls"][-1]
            report["status"] = str(last.get("status") or "tool_call_failed")
            report["next_actions"] = list(last.get("result", {}).get("next_actions", []))
            return _finish(report, report_path)
        if blocked:
            if _policy_skips_are_ok(plan, report["skipped_tool_calls"]):
                report["ok"] = True
                report["status"] = "ok_with_policy_skips"
                report["next_actions"] = [
                    "Safe non-hardware workflow recommendations executed.",
                    "Skipped read-only hardware-touching recommendations because allow_hardware=false.",
                ]
                return _finish(report, report_path)
            report["status"] = "execution_blocked_by_policy"
            report["next_actions"] = ["Review skipped_tool_calls[] and rerun with a policy that permits those safe actions."]
            return _finish(report, report_path)

        if plan.get("status") == "ready_for_nonvision_debug":
            report["ok"] = True
            report["status"] = "ok"
            report["next_actions"] = [
                "Safe non-vision workflow recommendations executed.",
                "Use explicit run mode with allow-flash/allow-repair only when that board operation is intended.",
            ]
            return _finish(report, report_path)

    report["status"] = "max_steps_reached"
    report["next_actions"] = ["Increase max_steps or inspect iterations[] and executed_tool_calls[] for the current stop point."]
    return _finish(report, report_path)


def _execution_decision(
    call: dict[str, Any],
    *,
    allow_file_writes: bool,
    allow_hardware: bool,
) -> dict[str, Any]:
    safety = call.get("safety", {})
    if safety.get("web_search_allowed"):
        return {"execute": False, "reason": "web_search_not_allowed"}
    if safety.get("vision_allowed"):
        return {"execute": False, "reason": "vision_not_allowed"}
    if safety.get("flash_allowed"):
        return {"execute": False, "reason": "flash_not_allowed"}
    if safety.get("repair_allowed"):
        return {"execute": False, "reason": "repair_not_allowed"}
    if safety.get("force_allowed"):
        return {"execute": False, "reason": "force_not_allowed"}
    if safety.get("target_register_write_allowed") or safety.get("target_memory_write_allowed"):
        return {"execute": False, "reason": "target_write_not_allowed"}
    if safety.get("requires_approval"):
        return {"execute": False, "reason": "approval_required"}
    if safety.get("writes_files") and not allow_file_writes:
        return {"execute": False, "reason": "file_writes_not_allowed"}
    if (safety.get("touches_hardware") or safety.get("target_control")) and not allow_hardware:
        return {"execute": False, "reason": "hardware_not_allowed"}
    return {"execute": True, "reason": "safe_by_policy"}


def _policy_skips_are_ok(plan: dict[str, Any], skipped_tool_calls: list[dict[str, Any]]) -> bool:
    if plan.get("status") != "ready_for_nonvision_debug":
        return False
    if not skipped_tool_calls:
        return False
    return all(item.get("decision", {}).get("reason") == "hardware_not_allowed" for item in skipped_tool_calls)


def _execute_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    from ai_mcu_debug import api

    tool = str(call.get("tool") or "")
    args = dict(call.get("arguments") or {})
    handlers: dict[str, Callable[..., dict[str, Any]]] = {
        "prepare_mcu_context": api.prepare_context,
        "check_mcu_context": api.check_prepared_context,
        "init_workspace": api.initialize_workspace,
        "workspace_status": api.get_workspace_status,
        "run_ai_debug": api.run_ai_debug,
        "accept_nonvision": api.accept_nonvision,
    }
    handler = handlers.get(tool)
    if handler is None:
        return {
            "ok": False,
            "status": "unsupported_workflow_tool",
            "tool": tool,
            "next_actions": ["Use workflow-plan output manually or add a workflow-run dispatcher for this tool."],
        }
    return handler(**args)


def _collect_artifacts(report: dict[str, Any], result: dict[str, Any]) -> None:
    for item in result.get("artifacts", []):
        if isinstance(item, dict) and item not in report["artifacts"]:
            report["artifacts"].append(item)
    for key, kind in {
        "output": "output",
        "config": "workspace_config",
        "state": "workspace_state",
        "report_path": "report",
        "manifest": "manifest",
    }.items():
        value = result.get(key)
        if value:
            item = {"kind": kind, "path": str(value)}
            if item not in report["artifacts"]:
                report["artifacts"].append(item)


def _finish(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    report["finished_at"] = _now()
    report["report_path"] = str(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
