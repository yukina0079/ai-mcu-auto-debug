from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.audit_log import append_audit_event


def sync_doc_repo(
    url: str | None,
    local_path: Path,
    ref: str | None = None,
    update: bool = True,
) -> dict[str, Any]:
    """Clone or update an MCU document repository.

    The repository is intentionally treated as a plain Git source of manifests
    and documents. It is not coupled to GitHub or to any specific hosting
    provider, so users can point it at a private repo, a local path, or a file
    URL.
    """

    commands: list[dict[str, Any]] = []
    if local_path.exists():
        if not _is_git_repo(local_path, commands):
            return {
                "ok": False,
                "status": "path_exists_not_git_repo",
                "url": url,
                "local_path": str(local_path),
                "commands": commands,
                "next_actions": ["Choose an empty local path or an existing Git checkout for the MCU document repo."],
            }
        status = "existing_repository"
        if update:
            pull = _run(["git", "-C", str(local_path), "pull", "--ff-only"], commands)
            if not pull["ok"]:
                return {
                    "ok": False,
                    "status": "update_failed",
                    "url": url,
                    "local_path": str(local_path),
                    "commands": commands,
                    "next_actions": ["Inspect the document repo checkout and resolve Git sync errors."],
                }
            status = "updated"
    else:
        if not url:
            return {
                "ok": False,
                "status": "missing_repo_url",
                "url": url,
                "local_path": str(local_path),
                "commands": commands,
                "next_actions": ["Provide --url for the MCU document repository."],
            }
        local_path.parent.mkdir(parents=True, exist_ok=True)
        clone = _run(["git", "clone", url, str(local_path)], commands)
        if not clone["ok"]:
            return {
                "ok": False,
                "status": "clone_failed",
                "url": url,
                "local_path": str(local_path),
                "commands": commands,
                "next_actions": ["Check the document repo URL and Git credentials."],
            }
        status = "cloned"

    if ref:
        checkout = _run(["git", "-C", str(local_path), "checkout", ref], commands)
        if not checkout["ok"]:
            return {
                "ok": False,
                "status": "checkout_failed",
                "url": url,
                "local_path": str(local_path),
                "ref": ref,
                "commands": commands,
                "next_actions": ["Check that the requested document repo ref exists."],
            }

    return {
        "ok": True,
        "status": status,
        "url": url,
        "local_path": str(local_path),
        "ref": ref,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "commands": commands,
    }


def _is_git_repo(path: Path, commands: list[dict[str, Any]]) -> bool:
    result = _run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"], commands)
    return bool(result["ok"] and result["stdout"].strip().lower() == "true")


def _run(command: list[str], commands: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        result = {
            "command": command,
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
        commands.append(result)
        append_audit_event(
            "doc_repo_command",
            args={"command": command},
            result=result,
            ok=False,
        )
        return result
    result = {
        "command": command,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    commands.append(result)
    append_audit_event(
        "doc_repo_command",
        args={"command": command},
        result=result,
        ok=bool(result["ok"]),
    )
    return result
