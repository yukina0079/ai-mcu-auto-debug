from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.workspace import load_workspace_defaults


DEFAULT_PATTERNS = (
    ".embeddedskills/*.json",
    "mcu_context*.json",
    "debug_runs/**/*.json",
    "debug_runs/**/*.jsonl",
    "debug_runs/**/*.log",
    "debug_runs/audit_events.jsonl",
    "debug_runs/**/*.md",
    "docs/**/*.md",
    "examples/docs/**/*.md",
    "knowledge_repos/**/*.md",
    "knowledge_cache/**/manifest.json",
    "knowledge_repos/**/manifest.json",
)


def export_handoff(
    output: Path,
    project_path: Path = Path("."),
    workspace_config: Path = Path(".embeddedskills/config.json"),
    report_dir: Path | None = None,
    include_globs: list[str] | None = None,
    zip_output: bool = False,
) -> dict[str, Any]:
    """Export a lightweight, replayable MCU debug handoff package."""

    root = project_path.resolve()
    workspace_config = workspace_config if workspace_config.is_absolute() else root / workspace_config
    package_dir = output if not zip_output else output.with_suffix("")
    package_dir = package_dir.resolve()
    if package_dir == root or _is_relative_to(root, package_dir):
        return {
            "ok": False,
            "status": "unsafe_output_path",
            "output": str(output),
            "project": str(root),
            "next_actions": ["Choose an output directory outside the project root or under debug_runs/handoff."],
        }
    if package_dir.exists():
        if package_dir.is_dir():
            shutil.rmtree(package_dir)
        else:
            package_dir.unlink()
    package_dir.mkdir(parents=True, exist_ok=True)

    defaults = load_workspace_defaults(workspace_config)
    patterns = list(DEFAULT_PATTERNS)
    if report_dir:
        patterns.extend(
            [
                f"{_relative_or_raw(report_dir, root)}/**/*.json",
                f"{_relative_or_raw(report_dir, root)}/**/*.jsonl",
                f"{_relative_or_raw(report_dir, root)}/**/*.log",
            ]
        )
    patterns.extend(include_globs or [])

    copied: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            if _is_relative_to(path.resolve(), package_dir.resolve()):
                continue
            if _is_existing_handoff_package_file(path, root):
                continue
            if _skip_large_binary(path):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            copied.append(_copy_artifact(path, root, package_dir))

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": str(root),
        "workspace_config": str(workspace_config),
        "defaults": defaults,
        "artifacts": copied,
        "replay": _replay_commands(defaults, workspace_config),
        "notes": [
            "This handoff package contains lightweight JSON/JSONL/log evidence only.",
            "Generated firmware binaries and downloaded vendor PDFs are intentionally excluded.",
            "Re-run commands from the original project checkout, not from inside the package directory.",
        ],
    }
    manifest_path = package_dir / "handoff_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    readme_path = package_dir / "README.md"
    readme_path.write_text(_readme(manifest), encoding="utf-8")

    archive_path: Path | None = None
    if zip_output:
        archive_path = output if output.suffix.lower() == ".zip" else output.with_suffix(".zip")
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in package_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package_dir))

    return {
        "ok": True,
        "output": str(archive_path or package_dir),
        "package_dir": str(package_dir),
        "zip": str(archive_path) if archive_path else None,
        "manifest": str(manifest_path),
        "artifacts": copied,
        "replay": manifest["replay"],
    }


def _copy_artifact(path: Path, root: Path, package_dir: Path) -> dict[str, Any]:
    relative = path.relative_to(root)
    destination = package_dir / "artifacts" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return {
        "source": str(path),
        "package_path": destination.relative_to(package_dir).as_posix(),
        "bytes": destination.stat().st_size,
        "kind": _kind(path),
    }


def _kind(path: Path) -> str:
    name = path.name.lower()
    if name == "ai_debug_report.json":
        return "ai_debug_report"
    if name.endswith(".knowledge.json"):
        return "knowledge_report"
    if name == "debug_commands.jsonl":
        return "debug_command_log"
    if name == "manifest.json" and "knowledge" in {part.lower() for part in path.parts}:
        return "knowledge_manifest"
    if ".embeddedskills" in {part.lower() for part in path.parts}:
        return "workspace_config"
    return "artifact"


def _skip_large_binary(path: Path, max_bytes: int = 5 * 1024 * 1024) -> bool:
    if path.stat().st_size > max_bytes:
        return True
    return path.suffix.lower() in {".pdf", ".elf", ".bin", ".hex", ".pack", ".zip"}


def _is_existing_handoff_package_file(path: Path, root: Path) -> bool:
    for parent in path.resolve().parents:
        if parent == root:
            return False
        if (parent / "handoff_manifest.json").is_file() and (parent / "artifacts").is_dir():
            return True
    return False


def _relative_or_raw(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _replay_commands(defaults: dict[str, Any], workspace_config: Path) -> list[list[str]]:
    commands: list[list[str]] = [
        ["python", "-m", "ai_mcu_debug.cli", "workspace-status", "--config", str(workspace_config)]
    ]
    knowledge_repo_url = defaults.get("knowledge_repo_url")
    knowledge_repo_path = defaults.get("knowledge_repo_path")
    if knowledge_repo_url and knowledge_repo_path:
        commands.append(
            [
                "python",
                "-m",
                "ai_mcu_debug.cli",
                "doc-repo-sync",
                "--url",
                str(knowledge_repo_url),
                "--local-path",
                str(knowledge_repo_path),
            ]
        )
    prepare = ["python", "-m", "ai_mcu_debug.cli", "prepare-mcu"]
    if defaults.get("project"):
        prepare.extend(["--project", str(defaults["project"])])
    if defaults.get("chip"):
        prepare.extend(["--chip", str(defaults["chip"])])
    if defaults.get("context"):
        prepare.extend(["--output", str(defaults["context"])])
    if knowledge_repo_path:
        prepare.extend(["--doc-repo", str(knowledge_repo_path)])
    commands.append(prepare)
    commands.append(
        [
            "python",
            "-m",
            "ai_mcu_debug.cli",
            "ai-debug",
            "--mode",
            "dry-run",
            "--workspace-config",
            str(workspace_config),
        ]
    )
    workflow_run = [
        "python",
        "-m",
        "ai_mcu_debug.cli",
        "workflow-run",
        "--workspace-config",
        str(workspace_config),
        "--no-hardware",
    ]
    if defaults.get("project"):
        workflow_run.extend(["--project", str(defaults["project"])])
    if defaults.get("chip"):
        workflow_run.extend(["--chip", str(defaults["chip"])])
    if defaults.get("context"):
        workflow_run.extend(["--context", str(defaults["context"])])
    commands.append(workflow_run)
    return commands


def _readme(manifest: dict[str, Any]) -> str:
    lines = [
        "# MCU Debug Handoff Package",
        "",
        f"Generated at: `{manifest['generated_at']}`",
        f"Project: `{manifest['project']}`",
        "",
        "## Replay Commands",
        "",
    ]
    for command in manifest["replay"]:
        lines.append("```powershell")
        lines.append(" ".join(command))
        lines.append("```")
    lines.extend(["", "## Artifacts", ""])
    for artifact in manifest["artifacts"]:
        lines.append(f"- `{artifact['kind']}`: `{artifact['package_path']}`")
    return "\n".join(lines) + "\n"
