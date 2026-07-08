from __future__ import annotations

import ast
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "realtime_debug",
        "phase": "phase1",
        "description": "Read/write registers and memory, reset, breakpoints, step, and debug sequences.",
        "cli": {"debug-op", "debug-sequence", "debug", "accept-first-stage"},
        "api": {"run_debug_op", "read_hardware_id"},
        "mcp": {"debug_op_guarded", "read_hardware_id"},
        "tests": {"tests/test_realtime_ops.py", "tests/test_debug_session.py", "tests/test_debug_sequence.py"},
        "docs": {"core registers", "memory reads", "breakpoints", "single-step"},
    },
    {
        "id": "build_test_repair_loop",
        "phase": "phase1",
        "description": "Build, smoke test, runtime log, explicit repair loop, and ai-debug orchestration.",
        "cli": {"build", "smoke-test", "runtime-log", "repair-build", "ai-debug"},
        "api": {"build_firmware", "smoke_test_firmware", "collect_runtime_log", "repair_build", "run_ai_debug"},
        "mcp": {"build_firmware", "smoke_test_firmware", "collect_runtime_log", "repair_build", "run_ai_debug"},
        "tests": {"tests/test_build_loop.py", "tests/test_ai_debug.py", "tests/test_api.py"},
        "docs": {"--allow-repair", "--allow-flash", "runtime-log"},
    },
    {
        "id": "knowledge_guard",
        "phase": "phase2",
        "description": "Generate MCU context, query/explain registers, and guard unsafe writes.",
        "cli": {
            "prepare-mcu",
            "check-context",
            "knowledge-query",
            "explain-register",
            "validate-register-write",
            "validate-address-write",
            "write-mcu-debug-doc",
        },
        "api": {"prepare_context", "check_prepared_context", "write_debug_record"},
        "mcp": {"prepare_mcu_context", "check_mcu_context", "write_debug_record"},
        "tests": {"tests/test_prepare_mcu.py", "tests/test_knowledge.py", "tests/test_cli_guard.py"},
        "docs": {"mcu_context", "anti-hallucination", "Unknown addresses are blocked"},
    },
    {
        "id": "user_document_intake",
        "phase": "phase2_5",
        "description": "Ask for user-provided documents/repos, fetch/cache them, and ingest context without web guessing.",
        "cli": {
            "resolve-chip",
            "doc-intake",
            "mcu-profile",
            "manifest-lint",
            "locate-docs",
            "doc-repo-sync",
            "fetch-docs",
            "ingest-docs",
        },
        "api": {
            "resolve_mcu_chip",
            "plan_docs",
            "get_mcu_profile",
            "lint_mcu_manifest",
            "locate_mcu_documents",
            "sync_document_repo",
            "fetch_user_documents",
            "ingest_user_documents",
        },
        "mcp": {
            "resolve_chip",
            "plan_document_intake",
            "mcu_profile",
            "lint_mcu_manifest",
            "locate_documents",
            "sync_document_repo",
            "fetch_user_documents",
            "ingest_documents",
        },
        "tests": {"tests/test_doc_fetch.py", "tests/test_doc_repo.py", "tests/test_profiles.py"},
        "docs": {"Do not run web search", "user-provided", "document Git repository"},
    },
    {
        "id": "safe_workflow_orchestration",
        "phase": "phase2_5",
        "description": "Plan and execute safe next steps through workflow-plan/workflow-run.",
        "cli": {"workflow-plan", "workflow-run", "setup-project", "init-workspace", "workspace-status", "accept-nonvision"},
        "api": {"plan_next_workflow", "run_next_workflow", "setup_project", "initialize_workspace", "accept_nonvision"},
        "mcp": {"workflow_plan", "workflow_run", "setup_project", "init_workspace", "workspace_status", "accept_nonvision"},
        "tests": {"tests/test_workflow_plan.py", "tests/test_workflow_run.py", "tests/test_bootstrap.py", "tests/test_nonvision_acceptance.py"},
        "docs": {"workflow-run", "recommended_tool_calls", "safety"},
    },
    {
        "id": "handoff_replay_audit",
        "phase": "phase4",
        "description": "Export replayable evidence packages and safely validate or execute non-hardware replay commands.",
        "cli": {"export-handoff", "replay-handoff"},
        "api": {"export_debug_handoff", "replay_debug_handoff"},
        "mcp": {"export_handoff", "replay_handoff"},
        "tests": {"tests/test_audit.py", "tests/test_replay.py"},
        "docs": {"workflow-run --no-hardware", "replay-handoff", "audit_events.jsonl"},
    },
    {
        "id": "skill_deployment",
        "phase": "phase4",
        "description": "Install/update the Codex skill, generate AI client MCP wiring, smoke-test the server, and run a single bootstrap gate.",
        "cli": {"install-skill", "mcp-config", "mcp-smoke", "skill-bootstrap"},
        "api": {"install_skill_package", "generate_mcp_client_config", "smoke_test_mcp_server", "bootstrap_skill"},
        "mcp": {"install_skill", "mcp_config", "mcp_smoke", "skill_bootstrap"},
        "tests": {"tests/test_skill_install.py", "tests/test_mcp_config.py", "tests/test_mcp_smoke.py", "tests/test_skill_bootstrap.py"},
        "docs": {"install-skill", "mcp-config", "mcp-smoke", "skill-bootstrap", "mcu-auto-debug"},
    },
    {
        "id": "safety_policy",
        "phase": "cross_cutting",
        "description": "Keep dangerous flash, repair, force, hardware replay, and target writes behind explicit gates.",
        "cli": {"ai-debug", "debug-op", "replay-handoff", "workflow-run"},
        "api": {"run_ai_debug", "run_debug_op", "replay_debug_handoff", "run_next_workflow"},
        "mcp": {"run_ai_debug", "debug_op_guarded", "replay_handoff", "workflow_run"},
        "tests": {"tests/test_cli_guard.py", "tests/test_replay.py", "tests/test_workflow_run.py", "tests/test_mcp_server.py"},
        "docs": {"--allow-flash", "--allow-repair", "--force", "standalone flash remains intentionally outside MCP"},
        "special_checks": {"no_standalone_flash_mcp", "workflow_run_no_hardware_replay"},
    },
)


VISION_CAPABILITY = {
    "id": "vision_loop",
    "phase": "phase3",
    "description": "Camera/image-based board state analysis.",
    "status": "postponed",
    "ok": False,
    "blocking": False,
    "missing": ["Vision phase is intentionally postponed by project policy."],
    "evidence": [],
}


def audit_capabilities(
    *,
    project_path: Path = ROOT,
    include_vision: bool = False,
    output: Path | None = None,
) -> dict[str, Any]:
    project_path = project_path.resolve()
    cli_commands = _cli_commands(project_path)
    api_functions = _api_functions()
    mcp_tools = _mcp_tools(project_path)
    tracked_files = _tracked_files(project_path)
    docs_text = _docs_text(project_path)

    capabilities = [
        _audit_capability(
            item,
            project_path=project_path,
            cli_commands=cli_commands,
            api_functions=api_functions,
            mcp_tools=mcp_tools,
            tracked_files=tracked_files,
            docs_text=docs_text,
        )
        for item in CAPABILITIES
    ]
    if include_vision:
        capabilities.append(dict(VISION_CAPABILITY, blocking=True))
    else:
        capabilities.append(dict(VISION_CAPABILITY))

    required = [item for item in capabilities if item.get("blocking", True)]
    ok = all(item.get("ok") for item in required)
    report: dict[str, Any] = {
        "ok": ok,
        "status": "nonvision_ready" if ok else "capability_gaps_found",
        "project": str(project_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "nonvision_required": True,
            "vision_required": include_vision,
            "vision_postponed": not include_vision,
        },
        "summary": {
            "capabilities_total": len(capabilities),
            "capabilities_ok": sum(1 for item in capabilities if item.get("ok")),
            "blocking_total": len(required),
            "blocking_ok": sum(1 for item in required if item.get("ok")),
            "cli_commands_found": len(cli_commands),
            "mcp_tools_found": len(mcp_tools),
        },
        "capabilities": capabilities,
        "policy": {
            "web_search_allowed": False,
            "flash_allowed_by_default": False,
            "repair_allowed_by_default": False,
            "force_allowed_by_default": False,
            "vision_allowed": include_vision,
        },
        "verification_commands": [
            "python -m pytest",
            "python -m ai_mcu_debug.cli mcp-smoke --project .",
            "python -m ai_mcu_debug.cli capability-audit",
            "python -m ai_mcu_debug.cli workflow-run --project . --chip <chip> --no-hardware",
        ],
        "next_actions": _next_actions(capabilities),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report["report_path"] = str(output)
    return report


def _audit_capability(
    capability: dict[str, Any],
    *,
    project_path: Path,
    cli_commands: set[str],
    api_functions: set[str],
    mcp_tools: set[str],
    tracked_files: set[str],
    docs_text: str,
) -> dict[str, Any]:
    required_cli = set(capability.get("cli", set()))
    required_api = set(capability.get("api", set()))
    required_mcp = set(capability.get("mcp", set()))
    required_tests = set(capability.get("tests", set()))
    required_docs = set(capability.get("docs", set()))

    missing: list[str] = []
    evidence: list[dict[str, Any]] = []
    _check_set("cli", required_cli, cli_commands, missing, evidence)
    _check_set("api", required_api, api_functions, missing, evidence)
    _check_set("mcp", required_mcp, mcp_tools, missing, evidence)
    _check_set("tests", required_tests, tracked_files, missing, evidence)
    for phrase in sorted(required_docs):
        if phrase.lower() in docs_text:
            evidence.append({"kind": "docs", "value": phrase})
        else:
            missing.append(f"docs:{phrase}")
    for check in sorted(capability.get("special_checks", set())):
        ok, detail = _special_check(check, mcp_tools=mcp_tools, docs_text=docs_text)
        if ok:
            evidence.append({"kind": "special_check", "value": check, "detail": detail})
        else:
            missing.append(f"special_check:{check}:{detail}")

    ok = not missing
    return {
        "id": capability["id"],
        "phase": capability["phase"],
        "description": capability["description"],
        "ok": ok,
        "status": "ok" if ok else "missing_evidence",
        "blocking": True,
        "missing": missing,
        "evidence": evidence,
    }


def _check_set(
    kind: str,
    required: set[str],
    actual: set[str],
    missing: list[str],
    evidence: list[dict[str, Any]],
) -> None:
    for value in sorted(required):
        if value in actual:
            evidence.append({"kind": kind, "value": value})
        else:
            missing.append(f"{kind}:{value}")


def _special_check(check: str, *, mcp_tools: set[str], docs_text: str) -> tuple[bool, str]:
    if check == "no_standalone_flash_mcp":
        return "flash" not in mcp_tools, "flash tool absent from MCP"
    if check == "workflow_run_no_hardware_replay":
        ok = "workflow-run --no-hardware" in docs_text and "replay_workflow_run_may_touch_hardware" in docs_text
        return ok, "workflow-run replay requires --no-hardware"
    return False, "unknown special check"


def _cli_commands(project_path: Path) -> set[str]:
    cli_path = project_path / "ai_mcu_debug" / "cli.py"
    if not cli_path.exists():
        return set()
    text = cli_path.read_text(encoding="utf-8")
    return set(re.findall(r"subparsers\.add_parser\(\"([^\"]+)\"", text))


def _api_functions() -> set[str]:
    from ai_mcu_debug import api

    return {name for name in dir(api) if not name.startswith("_") and callable(getattr(api, name))}


def _mcp_tools(project_path: Path) -> set[str]:
    server_path = project_path / "ai_mcu_debug" / "mcp_server.py"
    if not server_path.exists():
        return set()
    tree = ast.parse(server_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "TOOLS" for target in node.targets):
            if isinstance(node.value, ast.Dict):
                return {key.value for key in node.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "TOOLS":
            if isinstance(node.value, ast.Dict):
                return {key.value for key in node.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    return set()


def _tracked_files(project_path: Path) -> set[str]:
    ignored_dirs = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "build",
        "debug_runs",
        ".embeddedskills",
        "knowledge_cache",
        "knowledge_repos",
    }
    files: set[str] = set()
    for root, dirs, names in os.walk(project_path):
        dirs[:] = [name for name in dirs if name not in ignored_dirs]
        root_path = Path(root)
        for name in names:
            files.add(str((root_path / name).relative_to(project_path)).replace("\\", "/"))
    return files


def _docs_text(project_path: Path) -> str:
    parts: list[str] = []
    for path in [
        project_path / "README.md",
        project_path / "skills" / "mcu-auto-debug" / "SKILL.md",
        project_path / "skills" / "mcu-auto-debug" / "REFERENCE.md",
        project_path / "ai_mcu_debug" / "replay.py",
    ]:
        if path.exists():
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts).lower()


def _next_actions(capabilities: list[dict[str, Any]]) -> list[str]:
    missing = [item for item in capabilities if item.get("blocking", True) and not item.get("ok")]
    if not missing:
        return [
            "Non-vision automation surface is capability-complete by static audit.",
            "Run python -m pytest and a project-specific workflow-run/accept-nonvision gate for runtime verification.",
        ]
    return [f"Complete missing evidence for {item['id']}: {', '.join(item.get('missing', []))}" for item in missing]
