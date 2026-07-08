from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify mcu-auto-debug in a fresh workspace.")
    parser.add_argument("--output-root", default="debug_runs/cross_workspace_acceptance")
    parser.add_argument("--chip", default="STM32F103RCT6")
    parser.add_argument("--source-project", default="examples/firmware/stm32f103_blinky")
    parser.add_argument("--doc-repo-url")
    parser.add_argument("--doc-repo-local-path", default="knowledge_repos/mcu-knowledge-base")
    parser.add_argument("--doc-repo-only", action="store_true")
    parser.add_argument("--skip-ai-debug", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    run_dir = Path(args.output_root) / datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    workspace = run_dir / "workspace"
    project = workspace / "project"
    report_path = run_dir / "cross_workspace_acceptance.json"
    run_dir.mkdir(parents=True, exist_ok=False)

    _copy_tree(repo_root / args.source_project, project)
    if not args.doc_repo_only:
        _copy_tree(repo_root / "examples" / "docs", workspace / "examples" / "docs")
        _copy_tree(repo_root / "examples" / "svd", workspace / "examples" / "svd")
    elif not args.doc_repo_url and not (workspace / args.doc_repo_local_path).exists():
        report = {
            "ok": False,
            "workspace": str(workspace),
            "chip": args.chip,
            "status": "doc_repo_only_requires_url_or_existing_checkout",
            "next_actions": ["Pass --doc-repo-url or pre-populate --doc-repo-local-path inside the fresh workspace."],
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"ok": False, "report": str(report_path), "workspace": str(workspace)}, indent=2))
        return 1

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    commands: list[list[str]] = []
    doc_repo_path = Path(args.doc_repo_local_path)
    if args.doc_repo_url:
        commands.append(
            [
                sys.executable,
                "-m",
                "ai_mcu_debug.cli",
                "doc-repo-sync",
                "--url",
                args.doc_repo_url,
                "--local-path",
                str(doc_repo_path),
            ]
        )

    prepare_command = [
            sys.executable,
            "-m",
            "ai_mcu_debug.cli",
            "prepare-mcu",
            "--chip",
            args.chip,
            "--project",
            "project",
            "--output",
            "mcu_context.json",
    ]
    if args.doc_repo_url or args.doc_repo_only:
        prepare_command.extend(["--doc-repo", str(doc_repo_path)])
    commands.append(prepare_command)

    init_command = [
            sys.executable,
            "-m",
            "ai_mcu_debug.cli",
            "init-workspace",
            "--project",
            "project",
            "--chip",
            args.chip,
            "--context",
            "mcu_context.json",
            "--force",
    ]
    if args.doc_repo_url or args.doc_repo_only:
        if args.doc_repo_url:
            init_command.extend(["--knowledge-repo-url", args.doc_repo_url])
        init_command.extend(["--knowledge-repo-path", str(doc_repo_path)])
    commands.append(init_command)
    commands.append([sys.executable, "-m", "ai_mcu_debug.cli", "workspace-status"])
    if not args.skip_ai_debug:
        commands.append(
            [
                sys.executable,
                "-m",
                "ai_mcu_debug.cli",
                "ai-debug",
                "--mode",
                "dry-run",
                "--report-dir",
                "debug_runs/ai_debug_dry",
            ]
        )

    results: list[dict[str, Any]] = []
    ok = True
    for command in commands:
        completed = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True, check=False)
        item = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "ok": completed.returncode == 0,
        }
        results.append(item)
        print(f"+ {' '.join(command)}")
        if completed.stdout:
            print(completed.stdout.rstrip())
        if completed.stderr:
            print(completed.stderr.rstrip(), file=sys.stderr)
        if completed.returncode != 0:
            ok = False
            break

    report = {
        "ok": ok,
        "workspace": str(workspace),
        "chip": args.chip,
        "doc_repo_url": args.doc_repo_url,
        "doc_repo_local_path": str(doc_repo_path) if args.doc_repo_url or args.doc_repo_only else None,
        "doc_repo_only": args.doc_repo_only,
        "commands": results,
        "artifacts": _artifacts(workspace, report_path),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": ok, "report": str(report_path), "workspace": str(workspace)}, indent=2))
    return 0 if ok else 1


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    shutil.copytree(source, destination)


def _artifacts(workspace: Path, report_path: Path) -> list[dict[str, str]]:
    paths = [
        workspace / "mcu_context.json",
        workspace / ".embeddedskills" / "config.json",
        workspace / ".embeddedskills" / "build.json",
        workspace / ".embeddedskills" / "debug.target.json",
        workspace / ".embeddedskills" / "debug_task.json",
        workspace / "debug_runs" / "ai_debug_dry" / "ai_debug_report.json",
        workspace / "debug_runs" / "audit_events.jsonl",
        report_path,
    ]
    return [{"path": str(path)} for path in paths if path.exists()]


if __name__ == "__main__":
    sys.exit(main())
