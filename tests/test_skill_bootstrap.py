from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.api import bootstrap_skill
from ai_mcu_debug.skill_bootstrap import bootstrap_skill_environment


ROOT = Path(__file__).resolve().parents[1]


def test_skill_bootstrap_dry_run_does_not_write_outputs(tmp_path: Path) -> None:
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"
    config_output = tmp_path / "mcp.toml"
    report_output = tmp_path / "bootstrap.json"

    report = bootstrap_skill_environment(
        project_path=ROOT,
        destination=destination,
        config_output=config_output,
        report_output=report_output,
        dry_run=True,
    )

    assert report["ok"] is True
    assert report["status"] == "would_bootstrap"
    assert report["steps"]["install_skill"]["status"] == "would_install"
    assert report["steps"]["mcp_smoke"]["status"] == "ok"
    assert report["steps"]["capability_audit"]["status"] == "nonvision_ready"
    assert not destination.exists()
    assert not config_output.exists()
    assert not report_output.exists()


def test_skill_bootstrap_installs_and_writes_requested_outputs(tmp_path: Path) -> None:
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"
    config_output = tmp_path / "mcp.toml"
    report_output = tmp_path / "bootstrap.json"

    report = bootstrap_skill_environment(
        project_path=ROOT,
        destination=destination,
        config_output=config_output,
        report_output=report_output,
        force=True,
    )

    assert report["ok"] is True
    assert report["status"] == "bootstrapped"
    assert (destination / "SKILL.md").exists()
    assert "[mcp_servers.ai_mcu_debug]" in config_output.read_text(encoding="utf-8")
    assert report_output.exists()


def test_skill_bootstrap_dry_run_previews_installed_skill_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("local older skill", encoding="utf-8")

    report = bootstrap_skill_environment(project_path=ROOT, destination=destination, dry_run=True)

    assert report["ok"] is True
    files = {item["path"]: item for item in report["steps"]["install_skill"]["files"]}
    assert files["SKILL.md"]["action"] == "would_overwrite"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "local older skill"
    assert any("--force" in action for action in report["next_actions"])


def test_skill_bootstrap_api_can_skip_install() -> None:
    report = bootstrap_skill(project=ROOT, skip_install=True)

    assert report["ok"] is True
    assert report["steps"]["install_skill"]["status"] == "skipped"
