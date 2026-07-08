from __future__ import annotations

import subprocess
from pathlib import Path

from ai_mcu_debug.knowledge.doc_repo import sync_doc_repo


def test_sync_doc_repo_clones_local_git_repo(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=source, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True, capture_output=True, text=True)
    (source / "README.md").write_text("# MCU Docs\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=source, check=True, capture_output=True, text=True)

    checkout = tmp_path / "checkout"
    report = sync_doc_repo(url=str(source), local_path=checkout)

    assert report["ok"] is True
    assert report["status"] == "cloned"
    assert (checkout / "README.md").exists()


def test_sync_doc_repo_rejects_non_git_existing_path(tmp_path: Path) -> None:
    checkout = tmp_path / "not_git"
    checkout.mkdir()

    report = sync_doc_repo(url="https://example.invalid/repo.git", local_path=checkout)

    assert report["ok"] is False
    assert report["status"] == "path_exists_not_git_repo"
