from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.skill_install import install_skill


def test_install_skill_dry_run_does_not_write_files(tmp_path: Path) -> None:
    source = _skill_source(tmp_path, content="skill v1")
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"

    report = install_skill(source=source, destination=destination, dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "would_install"
    assert report["files"][0]["action"] == "would_copy"
    assert not destination.exists()


def test_install_skill_copies_source_package(tmp_path: Path) -> None:
    source = _skill_source(tmp_path, content="skill v1")
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"

    report = install_skill(source=source, destination=destination)

    assert report["ok"] is True
    assert report["status"] == "installed"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "skill v1"
    assert (destination / "REFERENCE.md").read_text(encoding="utf-8") == "reference"
    assert {item["path"] for item in report["files"]} == {"SKILL.md", "REFERENCE.md"}


def test_install_skill_blocks_overwriting_different_destination_without_force(tmp_path: Path) -> None:
    source = _skill_source(tmp_path, content="skill v1")
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("local edit", encoding="utf-8")

    report = install_skill(source=source, destination=destination)

    assert report["ok"] is False
    assert report["status"] == "destination_differs"
    assert report["conflicts"][0]["path"] == "SKILL.md"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "local edit"


def test_install_skill_force_overwrites_different_destination(tmp_path: Path) -> None:
    source = _skill_source(tmp_path, content="skill v1")
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("local edit", encoding="utf-8")

    report = install_skill(source=source, destination=destination, force=True)

    assert report["ok"] is True
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "skill v1"
    copied = {item["path"]: item for item in report["files"]}
    assert copied["SKILL.md"]["action"] == "overwrite"


def _skill_source(tmp_path: Path, *, content: str) -> Path:
    source = tmp_path / "source_skill"
    source.mkdir()
    (source / "SKILL.md").write_text(content, encoding="utf-8")
    (source / "REFERENCE.md").write_text("reference", encoding="utf-8")
    return source
