from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any


DEFAULT_SKILL_NAME = "mcu-auto-debug"


def install_skill(
    *,
    source: str | Path | None = None,
    destination: str | Path | None = None,
    codex_home: str | Path | None = None,
    skill_name: str = DEFAULT_SKILL_NAME,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Install or update the local Codex skill package with hash-based guardrails."""

    source_dir = Path(source) if source else _repo_root() / "skills" / skill_name
    destination_dir = _destination_dir(destination=destination, codex_home=codex_home, skill_name=skill_name)
    if not source_dir.exists():
        return {
            "ok": False,
            "status": "source_missing",
            "source": str(source_dir),
            "destination": str(destination_dir),
            "next_actions": ["Run from the ai-mcu-debug repository or pass --source to the skill directory."],
        }
    if not (source_dir / "SKILL.md").exists():
        return {
            "ok": False,
            "status": "skill_manifest_missing",
            "source": str(source_dir),
            "destination": str(destination_dir),
            "next_actions": ["Provide a source directory containing SKILL.md."],
        }

    source_files = _iter_source_files(source_dir)
    file_reports: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for source_file in source_files:
        relative = source_file.relative_to(source_dir).as_posix()
        target_file = destination_dir / relative
        source_hash = _sha256(source_file)
        target_hash = _sha256(target_file) if target_file.exists() else None
        action = _planned_action(target_file, source_hash, target_hash, force=force, dry_run=dry_run)
        report = {
            "path": relative,
            "source": str(source_file),
            "destination": str(target_file),
            "sha256": source_hash,
            "bytes": source_file.stat().st_size,
            "action": action,
        }
        if target_hash:
            report["existing_sha256"] = target_hash
        file_reports.append(report)
        if action == "conflict":
            conflicts.append(report)

    if conflicts:
        return {
            "ok": False,
            "status": "destination_differs",
            "source": str(source_dir),
            "destination": str(destination_dir),
            "files": file_reports,
            "conflicts": conflicts,
            "next_actions": ["Review destination changes, then rerun with --force if replacing them is intended."],
        }

    if not dry_run:
        destination_dir.mkdir(parents=True, exist_ok=True)
        for report in file_reports:
            if report["action"] in {"copy", "overwrite"}:
                target_file = Path(report["destination"])
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(report["source"], target_file)

    return {
        "ok": True,
        "status": "would_install" if dry_run else "installed",
        "source": str(source_dir),
        "destination": str(destination_dir),
        "skill_name": skill_name,
        "dry_run": dry_run,
        "force": force,
        "files": file_reports,
    }


def _destination_dir(
    *,
    destination: str | Path | None,
    codex_home: str | Path | None,
    skill_name: str,
) -> Path:
    if destination:
        return Path(destination)
    home = Path(codex_home) if codex_home else Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return home / "skills" / skill_name


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iter_source_files(source_dir: Path) -> list[Path]:
    ignored_dirs = {"__pycache__", ".pytest_cache"}
    files: list[Path] = []
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored_dirs for part in path.relative_to(source_dir).parts):
            continue
        files.append(path)
    return sorted(files)


def _planned_action(
    target_file: Path,
    source_hash: str,
    target_hash: str | None,
    *,
    force: bool,
    dry_run: bool,
) -> str:
    if target_hash is None:
        return "would_copy" if dry_run else "copy"
    if target_hash == source_hash:
        return "unchanged"
    if not force:
        return "conflict"
    return "would_overwrite" if dry_run else "overwrite"


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()
