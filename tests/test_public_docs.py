from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "docs/AGENT_QUICKSTART.md",
    ROOT / "docs/AI_AGENT_USAGE.md",
    ROOT / "docs/AI_LAB_MODEL.md",
    ROOT / "docs/GOLDEN_SUITES.md",
    ROOT / "docs/REPORTS.md",
    ROOT / "docs/VERIFIED_BOARDS.md",
    ROOT / "skills/mcu-auto-debug/SKILL.md",
]
MOJIBAKE_MARKERS = ["鐢", "鍜", "绋", "銆", "乭", "丆"]


def test_public_docs_have_no_obvious_mojibake() -> None:
    for path in PUBLIC_DOCS:
        text = path.read_text(encoding="utf-8")
        for marker in MOJIBAKE_MARKERS:
            assert marker not in text, f"{path} contains mojibake marker {marker}"


def test_readme_image_links_exist() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    image_paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)

    assert image_paths
    for image_path in image_paths:
        if image_path.startswith(("http://", "https://")):
            continue
        assert (ROOT / image_path).exists(), image_path


def test_readme_does_not_link_internal_comparison_doc() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "PROJECT_COMPARISON" not in text
    assert "EZ32Inc" not in text
