from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.api import get_mcu_profile, lint_mcu_manifest
from ai_mcu_debug.knowledge.profiles import lint_manifest, manifest_template, profile_for_chip
from ai_mcu_debug.knowledge.prepare import check_context, locate_docs


def test_profile_for_multiple_chip_families_returns_document_requirements() -> None:
    stm32 = profile_for_chip("STM32F407VGT6")
    nrf52 = profile_for_chip("nRF52840")
    rp2040 = profile_for_chip("RP2040")

    assert stm32["id"] == "stm32f4"
    assert nrf52["id"] == "nrf52"
    assert rp2040["id"] == "rp2040"
    assert any(group["name"] == "register_map" for group in nrf52["required_groups"])
    assert get_mcu_profile(chip="GD32F103C8T6")["profile"]["id"] == "gd32f1"


def test_manifest_template_never_includes_discovered_urls() -> None:
    template = manifest_template("nRF52840")

    assert template["vendor"] == "nordic"
    assert template["family"] == "nrf52"
    assert all("<user-provided" in item["source_url"] for item in template["documents"] if item.get("source_url"))


def test_lint_manifest_accepts_complete_manifest_with_reference_alias(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        documents=[
            ("product_specification", "documents/ps.md"),
            ("svd", "svd/device.svd"),
            ("linker", "linker/memory.ld"),
        ],
        chip="nRF52840",
        vendor="nordic",
        family="nrf52",
    )

    report = lint_manifest(manifest, chip="nRF52840", strict_hashes=True)

    assert report["ok"] is True
    assert report["profile"]["id"] == "nrf52"
    assert "reference_manual" in report["summary"]["document_kinds"]


def test_lint_manifest_reports_missing_required_document_group(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        documents=[
            ("datasheet", "documents/datasheet.md"),
            ("linker", "linker/memory.ld"),
        ],
        chip="STM32F103RCT6",
        vendor="st",
        family="stm32f1",
    )

    report = lint_mcu_manifest(manifest=manifest, chip="STM32F103RCT6")

    assert report["ok"] is False
    required = [item for item in report["diagnostics"] if item["code"] == "required_document_group_missing"]
    assert required[0]["group"] == "register_map"


def test_locate_and_context_accept_product_specification_as_reference(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(
        tmp_path,
        documents=[
            ("product_specification", "documents/ps.md"),
            ("svd", "svd/device.svd"),
            ("linker", "linker/memory.ld"),
        ],
        chip="nRF52840",
        vendor="nordic",
        family="nrf52",
    )

    report = locate_docs(project, chip="nRF52840", doc_repo_paths=[tmp_path / "mcu-docs"])

    assert report["ok"] is True
    assert any(item.get("manifest_path") == str(manifest) for item in report["documents"])
    assert not any(item["kind"] == "datasheet_or_reference" for item in report["missing"])

    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "chip": "nRF52840",
                "sources": {
                    "svd": "device.svd",
                    "documents": [{"kind": "product_specification", "path": "ps.md"}],
                },
                "register_index": {"GPIO.OUT": {"source": "svd"}},
                "memory_regions": [{"name": "RAM", "origin": 536870912, "length": 262144}],
                "risk_rules": {"dangerous_address_ranges": [{"name": "FLASH", "start": 0, "end": 4096}]},
            }
        ),
        encoding="utf-8",
    )
    assert check_context(context)["ok"] is True


def _write_manifest(
    tmp_path: Path,
    *,
    documents: list[tuple[str, str]],
    chip: str,
    vendor: str,
    family: str,
) -> Path:
    chip_dir = tmp_path / "mcu-docs" / "vendors" / vendor / family / chip
    manifest_documents = []
    for kind, local_path in documents:
        path = chip_dir / local_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{chip} {kind}", encoding="utf-8")
        digest = _sha256(path)
        manifest_documents.append({"kind": kind, "local_path": local_path, "local_sha256": digest})
    manifest = chip_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "chip": chip,
                "vendor": vendor,
                "family": family,
                "documents": manifest_documents,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
