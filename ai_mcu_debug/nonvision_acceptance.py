from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ai_mcu_debug.audit import export_handoff
from ai_mcu_debug.bootstrap import DoctorRunner, ProbeScanner, setup_project
from ai_mcu_debug.config import load_build_config
from ai_mcu_debug.doctor import run_doctor
from ai_mcu_debug.factory import create_build_adapter, create_repair_adapter
from ai_mcu_debug.probe_scan import scan_debug_probes
from ai_mcu_debug.replay import replay_handoff
from ai_mcu_debug.runner import AiDebugSession
from ai_mcu_debug.workspace import load_workspace_defaults


AiDebugRunner = Callable[..., dict[str, Any]]
HandoffExporter = Callable[..., dict[str, Any]]
HandoffReplayer = Callable[..., dict[str, Any]]


def run_nonvision_acceptance(
    *,
    project_path: Path = Path("."),
    output_dir: Path = Path(".embeddedskills"),
    context_path: Path = Path("examples/mcu_context.json"),
    report_dir: Path = Path("debug_runs/nonvision_acceptance"),
    handoff_output: Path | None = None,
    handoff_project_path: Path = Path("."),
    zip_handoff: bool = False,
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    board: str | None = None,
    package_name: str | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
    knowledge_repo_url: str | None = None,
    knowledge_repo_path: Path | None = None,
    build_config_path: Path | None = None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: Path | None = None,
    keil_target: str | None = None,
    uv4_path: Path | None = None,
    target_path: Path | None = None,
    task_path: Path | None = None,
    debug_backend: str | None = None,
    executable_path: Path | None = None,
    interface_cfg: str | None = None,
    target_cfg: str | None = None,
    transport: str = "swd",
    adapter_speed: int = 100,
    scan_probes: bool = True,
    force: bool = False,
    doctor_runner: DoctorRunner = run_doctor,
    probe_scanner: ProbeScanner = scan_debug_probes,
    ai_debug_runner: AiDebugRunner | None = None,
    handoff_exporter: HandoffExporter = export_handoff,
    handoff_replayer: HandoffReplayer = replay_handoff,
) -> dict[str, Any]:
    """Run the replayable non-vision acceptance chain.

    The chain is intentionally safe: setup, dry-run only, handoff export, then replay validation.
    It never flashes firmware, never runs repair, and never uses vision.
    """

    report_dir.mkdir(parents=True, exist_ok=True)
    acceptance_report_path = report_dir / "nonvision_acceptance_report.json"
    report: dict[str, Any] = {
        "ok": False,
        "status": "started",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "project": str(project_path),
        "context": str(context_path),
        "workspace_config": str(output_dir / "config.json"),
        "report_dir": str(report_dir),
        "policy": {
            "mode": "nonvision",
            "ai_debug_mode": "dry-run",
            "flash_allowed": False,
            "repair_allowed": False,
            "vision_allowed": False,
            "web_search_allowed": False,
            "handoff_replay_execute": False,
        },
        "steps": [],
        "artifacts": [{"kind": "nonvision_acceptance_report", "path": str(acceptance_report_path)}],
        "next_actions": [],
    }

    setup = setup_project(
        project_path=project_path,
        output_dir=output_dir,
        context_path=context_path,
        chip=chip,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        board=board,
        package_name=package_name,
        extra_docs=extra_docs,
        doc_repo_paths=doc_repo_paths,
        knowledge_repo_url=knowledge_repo_url,
        knowledge_repo_path=knowledge_repo_path,
        build_config_path=build_config_path,
        build_backend=build_backend,
        pio_env=pio_env,
        keil_project=keil_project,
        keil_target=keil_target,
        uv4_path=uv4_path,
        target_path=target_path,
        task_path=task_path,
        debug_backend=debug_backend,
        executable_path=executable_path,
        interface_cfg=interface_cfg,
        target_cfg=target_cfg,
        transport=transport,
        adapter_speed=adapter_speed,
        scan_probes=scan_probes,
        force=force,
        doctor_runner=doctor_runner,
        probe_scanner=probe_scanner,
    )
    report["setup_project"] = setup
    report["artifacts"].extend(setup.get("artifacts", []))
    _add_step(report, "setup-project", bool(setup.get("ok")), required=True, reason=setup.get("status"))
    if not setup.get("ok"):
        report["status"] = str(setup.get("status") or "setup_project_failed")
        report["next_actions"] = list(setup.get("next_actions", []))
        return _finish(report, acceptance_report_path)

    workspace_config = output_dir / "config.json"
    ai_report_dir = report_dir / "ai_debug_dry_run"
    if ai_debug_runner is None:
        ai_debug = _run_ai_debug_dry(
            project_path=project_path,
            context_path=context_path,
            workspace_config=workspace_config,
            report_dir=ai_report_dir,
            chip=chip,
            svd_path=svd_path,
            linker_path=linker_path,
            startup_path=startup_path,
            board=board,
            package_name=package_name,
            extra_docs=extra_docs,
            doc_repo_paths=doc_repo_paths,
            doctor_runner=doctor_runner,
            probe_scanner=probe_scanner,
        )
    else:
        ai_debug = ai_debug_runner(
            project_path=project_path,
            context_path=context_path,
            workspace_config=workspace_config,
            report_dir=ai_report_dir,
            chip=chip,
            svd_path=svd_path,
            linker_path=linker_path,
            startup_path=startup_path,
            board=board,
            package_name=package_name,
            extra_docs=extra_docs,
            doc_repo_paths=doc_repo_paths,
        )
    report["ai_debug"] = ai_debug
    _add_step(report, "ai-debug-dry-run", bool(ai_debug.get("ok")), required=True, reason=ai_debug.get("status"))
    _add_artifact_from_report_path(report, ai_debug, "ai_debug_report")
    if not ai_debug.get("ok"):
        report["status"] = str(ai_debug.get("status") or "ai_debug_dry_run_failed")
        report["next_actions"] = list(ai_debug.get("next_actions", []))
        return _finish(report, acceptance_report_path)

    _write_report(report, acceptance_report_path)
    handoff_path = handoff_output or (report_dir / ("handoff.zip" if zip_handoff else "handoff"))
    handoff = handoff_exporter(
        output=handoff_path,
        project_path=handoff_project_path,
        workspace_config=workspace_config,
        report_dir=report_dir,
        zip_output=zip_handoff,
    )
    report["handoff"] = handoff
    _add_step(report, "export-handoff", bool(handoff.get("ok")), required=True, reason=handoff.get("status"))
    _add_artifact_from_key(report, handoff, "manifest", "handoff_manifest")
    _add_artifact_from_key(report, handoff, "output", "handoff_package")
    if not handoff.get("ok"):
        report["status"] = str(handoff.get("status") or "handoff_export_failed")
        report["next_actions"] = list(handoff.get("next_actions", []))
        return _finish(report, acceptance_report_path)

    replay_report_path = report_dir / "replay_handoff_report.json"
    manifest_path = handoff.get("manifest")
    if not manifest_path:
        replay = {
            "ok": False,
            "status": "handoff_manifest_missing",
            "next_actions": ["Re-run export-handoff and verify the handoff manifest path is present."],
        }
    else:
        replay = handoff_replayer(
            manifest_path=Path(str(manifest_path)),
            project_path=handoff_project_path,
            execute=False,
            output_path=replay_report_path,
        )
    report["handoff_replay"] = replay
    _add_step(report, "replay-handoff-validate", bool(replay.get("ok")), required=True, reason=replay.get("status"))
    _add_artifact_from_key(report, replay, "report_path", "handoff_replay_report")
    if not replay.get("ok"):
        report["status"] = str(replay.get("status") or "handoff_replay_failed")
        report["next_actions"] = list(replay.get("next_actions", []))
        return _finish(report, acceptance_report_path)

    report["status"] = "ok"
    report["ok"] = True
    report["next_actions"] = [
        "Handoff replay commands were policy-validated and are ready for another AI or engineer.",
        "Use read-only or run mode separately only when hardware access and policy allow it.",
    ]
    return _finish(report, acceptance_report_path)


def _run_ai_debug_dry(
    *,
    project_path: Path,
    context_path: Path,
    workspace_config: Path,
    report_dir: Path,
    chip: str | None,
    svd_path: Path | None,
    linker_path: Path | None,
    startup_path: Path | None,
    board: str | None,
    package_name: str | None,
    extra_docs: list[tuple[str, Path]] | None,
    doc_repo_paths: list[Path] | None,
    doctor_runner: DoctorRunner,
    probe_scanner: ProbeScanner,
) -> dict[str, Any]:
    defaults = load_workspace_defaults(workspace_config)
    build_adapter = None
    repair_adapter = None
    build_config_path = defaults.get("build_config")
    if build_config_path:
        build_config = load_build_config(Path(str(build_config_path)))
        build_adapter = create_build_adapter(build_config)
        repair_adapter = create_repair_adapter(build_config)
    return AiDebugSession(
        project_path=Path(defaults.get("project") or project_path),
        context_path=Path(defaults.get("context") or context_path),
        mode="dry-run",
        prepare_options={
            "chip": chip or defaults.get("chip"),
            "svd_path": Path(defaults.get("svd") or svd_path) if (defaults.get("svd") or svd_path) else None,
            "linker_path": Path(defaults.get("linker") or linker_path) if (defaults.get("linker") or linker_path) else None,
            "startup_path": Path(defaults.get("startup") or startup_path) if (defaults.get("startup") or startup_path) else None,
            "board": board or defaults.get("board"),
            "package_name": package_name or defaults.get("package"),
            "extra_docs": extra_docs or [],
            "doc_repo_paths": doc_repo_paths or ([Path(str(defaults["knowledge_repo_path"]))] if defaults.get("knowledge_repo_path") else []),
        },
        build_adapter=build_adapter,
        repair_adapter=repair_adapter,
        report_dir=report_dir,
        allow_flash=False,
        allow_repair=False,
        doctor_runner=lambda: doctor_runner(defaults.get("debug_backend"), None),
        probe_scanner=probe_scanner,
    ).run()


def _add_step(report: dict[str, Any], name: str, ok: bool, required: bool, reason: object | None = None) -> None:
    report["steps"].append({"name": name, "ok": ok, "required": required, "reason": reason})


def _add_artifact_from_report_path(report: dict[str, Any], source: dict[str, Any], kind: str) -> None:
    path = source.get("report_path")
    if path:
        _add_artifact(report, kind, str(path))


def _add_artifact_from_key(report: dict[str, Any], source: dict[str, Any], key: str, kind: str) -> None:
    path = source.get(key)
    if path:
        _add_artifact(report, kind, str(path))


def _add_artifact(report: dict[str, Any], kind: str, path: str) -> None:
    item = {"kind": kind, "path": path}
    if item not in report["artifacts"]:
        report["artifacts"].append(item)


def _finish(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["report_path"] = str(report_path)
    _write_report(report, report_path)
    return report


def _write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
