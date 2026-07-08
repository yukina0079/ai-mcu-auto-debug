from __future__ import annotations

import json
import os
from pathlib import Path

from ai_mcu_debug.knowledge.prepare import check_context, locate_docs, plan_document_intake, prepare_mcu, resolve_chip


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER_RCT6 = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_resolve_chip_uses_explicit_chip() -> None:
    report = resolve_chip(PROJECT, chip="STM32F103RCT6", svd_path=SVD, linker_path=LINKER_RCT6)

    assert report["ok"] is True
    assert report["selected"] == "STM32F103RCT6"
    assert report["candidates"][0]["score"] >= 100


def test_resolve_chip_keeps_explicit_chip_when_project_contains_noisy_candidates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.json").write_text('{"related": ["STM32F103RC", "STM32F103RC", "STM32F103RC"]}', encoding="utf-8")

    report = resolve_chip(project, chip="STM32F103RCT6")

    assert report["ok"] is True
    assert report["selected"] == "STM32F103RCT6"


def test_resolve_chip_uses_svd_content_and_linker_capacity(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    svd = project / "device.svd"
    svd.write_text("<device><name>STM32F103xE</name></device>", encoding="utf-8")
    startup = project / "startup.c"
    startup.write_text("/* startup for STM32F103 family */", encoding="utf-8")
    linker = project / "linker.ld"
    linker.write_text(
        """
MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 256K
  RAM (rwx)  : ORIGIN = 0x20000000, LENGTH = 48K
}
""",
        encoding="utf-8",
    )

    report = resolve_chip(project, svd_path=svd, startup_path=startup, linker_path=linker)

    chips = {item["chip"]: item for item in report["candidates"]}
    assert "STM32F103XE" in chips
    assert "STM32F103XC" in chips
    assert report["selected"] == "STM32F103XC"
    assert any(item["source"] == "linker_memory_map" for item in chips["STM32F103XC"]["evidence"])


def test_resolve_chip_reports_ambiguous_equal_candidates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "startup_stm32f103c8.c").write_text("void Reset_Handler(void) {}", encoding="utf-8")
    (project / "startup_stm32f103rct6.c").write_text("void Reset_Handler(void) {}", encoding="utf-8")

    report = resolve_chip(project)

    assert report["ok"] is False
    assert report["selected"] is None
    assert report["ambiguous"] is True
    assert report["reason"] == "ambiguous_chip"


def test_locate_docs_records_sha256_for_local_documents() -> None:
    report = locate_docs(
        PROJECT,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER_RCT6,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )

    assert report["ok"] is True
    datasheet = next(item for item in report["documents"] if item["kind"] == "datasheet")
    assert datasheet["sha256"]
    assert len(datasheet["sha256"]) == 64


def test_locate_docs_does_not_treat_generated_debug_record_as_datasheet() -> None:
    report = locate_docs(
        PROJECT,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER_RCT6,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )

    paths = [Path(item["local_path"]).name for item in report["documents"] if item["kind"] == "datasheet"]
    assert "STM32F103_DEBUG_RECORD.md" not in paths


def test_locate_docs_does_not_treat_skill_reference_as_reference_manual(tmp_path: Path) -> None:
    project = tmp_path / "project"
    skill_dir = project / "skills" / "mcu-auto-debug"
    docs_dir = project / "docs"
    skill_dir.mkdir(parents=True)
    docs_dir.mkdir()
    (skill_dir / "REFERENCE.md").write_text("This is an agent skill reference, not an MCU RM0008 manual.", encoding="utf-8")
    datasheet = docs_dir / "stm32f103_datasheet_notes.md"
    datasheet.write_text("Flash memory starts at 0x08000000.", encoding="utf-8")
    errata = docs_dir / "stm32f103_errata_notes.md"
    errata.write_text("errata note", encoding="utf-8")
    svd = project / "STM32F103_min.svd"
    svd.write_text("<device/>", encoding="utf-8")
    linker = project / "linker.stm32f103rct6.ld"
    linker.write_text("MEMORY {}", encoding="utf-8")

    report = locate_docs(project, chip="STM32F103RCT6")

    reference_paths = [Path(item["local_path"]).name for item in report["documents"] if item["kind"] == "reference_manual"]
    assert "REFERENCE.md" not in reference_paths


def test_locate_docs_recognizes_flash_ld_linker_name(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    linker = project / "STM32F103RCTx_FLASH.ld"
    linker.write_text("MEMORY {}", encoding="utf-8")

    report = locate_docs(project, chip="STM32F103RCT6")

    linker_paths = [Path(item["local_path"]).name for item in report["documents"] if item["kind"] == "linker"]
    assert "STM32F103RCTx_FLASH.ld" in linker_paths


def test_resolve_chip_ignores_generated_debug_runs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "startup_stm32f103rct6.c").write_text("void Reset_Handler(void) {}", encoding="utf-8")
    debug_runs = project / "debug_runs"
    debug_runs.mkdir()
    (debug_runs / "old_report.json").write_text('{"chip": "STM32F407VG"}', encoding="utf-8")

    report = resolve_chip(project)

    chips = {item["chip"] for item in report["candidates"]}
    assert "STM32F407VG" not in chips
    assert report["selected"] == "STM32F103RCT6"


def test_prepare_mcu_generates_rct6_context(tmp_path: Path) -> None:
    output = tmp_path / "mcu_context.stm32f103rct6.json"

    report = prepare_mcu(
        project_path=PROJECT,
        output_path=output,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER_RCT6,
        startup_path=STARTUP,
        board="stm32f103rct6_daplink",
        package_name="LQFP64",
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )

    assert report["ok"] is True
    check = check_context(output)
    assert check["ok"] is True
    assert check["chip"] == "STM32F103RCT6"
    context = json.loads(output.read_text(encoding="utf-8"))
    regions = {region["name"]: region for region in context["memory_regions"]}
    assert regions["FLASH"]["length"] == 256 * 1024
    assert regions["RAM"]["length"] == 48 * 1024


def test_prepare_mcu_prefers_chip_specific_linker_over_generic_project_linker(tmp_path: Path) -> None:
    output = tmp_path / "context.json"

    report = prepare_mcu(
        project_path=PROJECT,
        output_path=output,
        chip="STM32F103RCT6",
        svd_path=SVD,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )

    assert report["ok"] is True
    context = json.loads(output.read_text(encoding="utf-8"))
    assert context["sources"]["linker"].lower().endswith("linker.stm32f103rct6.ld")
    regions = {region["name"]: region for region in context["memory_regions"]}
    assert regions["FLASH"]["length"] == 256 * 1024
    assert regions["RAM"]["length"] == 48 * 1024


def test_prepare_mcu_reports_missing_required_documents(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = prepare_mcu(project_path=project, output_path=tmp_path / "context.json", chip="STM32F103RCT6")

    assert report["ok"] is False
    assert report["status"] == "missing_required_document"
    missing = {item["kind"] for item in report["missing"]}
    assert "svd" in missing
    assert "linker" in missing
    assert any(action.startswith("Ask the user") for action in report["next_actions"])
    assert not any("allow fetching" in action for action in report["next_actions"])


def test_plan_document_intake_asks_for_specific_user_documents(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = plan_document_intake(project_path=project, chip="STM32F103RCT6", output_path=tmp_path / "context.json")

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    required = {item["kind"]: item for item in report["required_requests"]}
    assert {"svd", "linker", "datasheet_or_reference"} <= set(required)
    assert required["svd"]["question_zh"].startswith("请提供")
    assert report["policy"]["web_search_allowed"] is False
    assert "prepare-mcu" in report["commands"]["direct_prepare_template"]
    assert "为了生成可追溯的 MCU 知识库" in report["user_message_zh"]


def test_plan_document_intake_reports_ready_when_required_docs_exist() -> None:
    report = plan_document_intake(
        project_path=PROJECT,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER_RCT6,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )

    assert report["ok"] is True
    assert report["status"] == "ready_for_prepare_mcu"
    assert report["required_requests"] == []
    assert "必需资料已齐" in report["user_message_zh"]


def test_check_context_requires_dangerous_address_rules(tmp_path: Path) -> None:
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "sources": {
                    "svd": "device.svd",
                    "documents": [{"kind": "datasheet", "path": "datasheet.md"}],
                },
                "register_index": {"GPIOC.CRH": {"qualified_name": "GPIOC.CRH", "source": "device.svd"}},
                "memory_regions": [{"name": "RAM", "origin": 0x20000000, "length": 1024, "end": 0x20000400}],
                "risk_rules": {"dangerous_address_ranges": []},
            }
        ),
        encoding="utf-8",
    )

    report = check_context(context)

    assert report["ok"] is False
    missing = {item["kind"]: item for item in report["missing"]}
    assert missing["dangerous_address_ranges"]["required"] is True


def test_locate_docs_reuses_knowledge_cache_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "knowledge_cache" / "st" / "STM32F103RCT6"
    cache.mkdir(parents=True)
    datasheet = cache / "datasheet.md"
    datasheet.write_text("STM32F103RCT6 datasheet notes", encoding="utf-8")
    svd = cache / "device.svd"
    svd.write_text("<device/>", encoding="utf-8")
    linker = cache / "linker.ld"
    linker.write_text("MEMORY {}", encoding="utf-8")
    manifest = cache / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "documents": [
                    {"kind": "datasheet", "local_path": "datasheet.md", "source_url": "https://www.st.com/example.pdf"},
                    {"kind": "svd", "local_path": "device.svd"},
                    {"kind": "linker", "local_path": "linker.ld"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = locate_docs(project, chip="STM32F103RCT6")

    paths = {Path(item["local_path"]).name for item in report["documents"]}
    assert {"datasheet.md", "device.svd", "linker.ld"} <= paths
    datasheet_entry = next(item for item in report["documents"] if Path(item["local_path"]).name == "datasheet.md")
    assert datasheet_entry["manifest_path"] == str(manifest)
    assert datasheet_entry["source_url"] == "https://www.st.com/example.pdf"


def test_locate_docs_reads_doc_repo_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo_chip_dir = tmp_path / "mcu-docs" / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    repo_chip_dir.mkdir(parents=True)
    docs_dir = repo_chip_dir / "documents"
    docs_dir.mkdir()
    datasheet = docs_dir / "stm32f103rc_datasheet_notes.md"
    datasheet.write_text("STM32F103RCT6 datasheet notes", encoding="utf-8")
    svd = repo_chip_dir / "svd" / "STM32F103_min.svd"
    svd.parent.mkdir()
    svd.write_text("<device/>", encoding="utf-8")
    linker = repo_chip_dir / "linker" / "linker.stm32f103rct6.ld"
    linker.parent.mkdir()
    linker.write_text("MEMORY {}", encoding="utf-8")
    manifest = repo_chip_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "aliases": ["STM32F103RC"],
                "vendor": "st",
                "family": "stm32f1",
                "documents": [
                    {"kind": "datasheet", "local_path": "documents/stm32f103rc_datasheet_notes.md"},
                    {"kind": "svd", "local_path": "svd/STM32F103_min.svd"},
                    {"kind": "linker", "local_path": "linker/linker.stm32f103rct6.ld"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[tmp_path / "mcu-docs"])

    assert report["ok"] is True
    paths = {Path(item["local_path"]).name for item in report["documents"]}
    assert {"stm32f103rc_datasheet_notes.md", "STM32F103_min.svd", "linker.stm32f103rct6.ld"} <= paths
    datasheet_entry = next(item for item in report["documents"] if item.get("manifest_path") == str(manifest))
    assert datasheet_entry["trust_level"] == "doc_repo"
    assert datasheet_entry["manifest_path"] == str(manifest)


def test_locate_docs_reports_missing_doc_repo_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    repo.mkdir()

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert "manifest_missing" in diagnostics
    assert diagnostics["manifest_missing"]["blocks"] is False


def test_locate_docs_reports_missing_doc_repo_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "missing-docs"

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["doc_repo_path_missing"]["path"] == str(repo)


def test_locate_docs_reports_unsupported_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    chip_dir = repo / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    chip_dir.mkdir(parents=True)
    manifest = chip_dir / "manifest.json"
    manifest.write_text('{"schema_version": 99, "chip": "STM32F103RCT6", "documents": []}', encoding="utf-8")

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["unsupported_manifest"]["path"] == str(manifest)


def test_locate_docs_reports_invalid_json_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    chip_dir = repo / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    chip_dir.mkdir(parents=True)
    manifest = chip_dir / "manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["unsupported_manifest"]["reason"] == "manifest_json_cannot_be_read_or_parsed"
    assert diagnostics["unsupported_manifest"]["path"] == str(manifest)


def test_locate_docs_reports_documents_not_list_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    chip_dir = repo / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    chip_dir.mkdir(parents=True)
    manifest = chip_dir / "manifest.json"
    manifest.write_text('{"chip":"STM32F103RCT6","documents":{}}', encoding="utf-8")

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["unsupported_manifest"]["reason"] == "manifest_schema_missing_documents_list"


def test_locate_docs_reports_doc_repo_manifest_missing_chip_even_with_chip_filter(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    chip_dir = repo / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    chip_dir.mkdir(parents=True)
    manifest = chip_dir / "manifest.json"
    manifest.write_text('{"documents":[]}', encoding="utf-8")

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["reason"]: item for item in report["diagnostics"]}
    assert diagnostics["doc_repo_manifest_missing_chip"]["path"] == str(manifest)


def test_locate_docs_reports_doc_repo_no_matching_chip_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    chip_dir = repo / "vendors" / "st" / "stm32f1" / "STM32F103C8T6"
    chip_dir.mkdir(parents=True)
    (chip_dir / "manifest.json").write_text(
        '{"chip":"STM32F103C8T6","documents":[]}',
        encoding="utf-8",
    )

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[repo])

    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["chip_manifest_not_found"]["chip"] == "STM32F103RCT6"
    assert diagnostics["chip_manifest_not_found"]["blocks"] is False


def test_locate_docs_blocks_doc_repo_hash_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo_chip_dir = tmp_path / "mcu-docs" / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    docs_dir = repo_chip_dir / "documents"
    docs_dir.mkdir(parents=True)
    datasheet = docs_dir / "datasheet.md"
    datasheet.write_text("changed local notes", encoding="utf-8")
    svd = repo_chip_dir / "svd" / "device.svd"
    svd.parent.mkdir()
    svd.write_text("<device/>", encoding="utf-8")
    linker = repo_chip_dir / "linker" / "linker.ld"
    linker.parent.mkdir()
    linker.write_text("MEMORY {}", encoding="utf-8")
    (repo_chip_dir / "manifest.json").write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "documents": [
                    {
                        "kind": "datasheet",
                        "local_path": "documents/datasheet.md",
                        "local_sha256": "0" * 64,
                    },
                    {"kind": "svd", "local_path": "svd/device.svd"},
                    {"kind": "linker", "local_path": "linker/linker.ld"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[tmp_path / "mcu-docs"])

    assert report["ok"] is False
    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["hash_mismatch"]["blocks"] is True
    assert diagnostics["hash_mismatch"]["local_path"] == str(datasheet)


def test_locate_docs_does_not_block_source_url_sha256_for_local_notes(tmp_path: Path) -> None:
    current = Path.cwd()
    project = tmp_path / "project"
    project.mkdir()
    repo_chip_dir = tmp_path / "mcu-docs" / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    docs_dir = repo_chip_dir / "documents"
    docs_dir.mkdir(parents=True)
    datasheet = docs_dir / "datasheet.md"
    datasheet.write_text("lightweight local notes, not the vendor pdf", encoding="utf-8")
    svd = repo_chip_dir / "svd" / "device.svd"
    svd.parent.mkdir()
    svd.write_text("<device/>", encoding="utf-8")
    linker = repo_chip_dir / "linker" / "linker.ld"
    linker.parent.mkdir()
    linker.write_text("MEMORY {}", encoding="utf-8")
    (repo_chip_dir / "manifest.json").write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "documents": [
                    {
                        "kind": "datasheet",
                        "local_path": "documents/datasheet.md",
                        "source_url": "https://www.st.com/resource/en/datasheet/stm32f103rc.pdf",
                        "sha256": "0" * 64,
                    },
                    {"kind": "svd", "local_path": "svd/device.svd"},
                    {"kind": "linker", "local_path": "linker/linker.ld"},
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        # Keep the repo-local knowledge_cache from taking priority in this focused test.
        os.chdir(tmp_path)
        report = locate_docs(project, chip="STM32F103RCT6", doc_repo_paths=[tmp_path / "mcu-docs"])
    finally:
        os.chdir(current)

    assert report["ok"] is True
    assert not [item for item in report["diagnostics"] if item["code"] == "hash_mismatch"]
    datasheet_entry = next(
        item
        for item in report["documents"]
        if item["kind"] == "datasheet" and item.get("manifest_path")
    )
    assert datasheet_entry["source_sha256"] == "0" * 64


def test_locate_docs_warns_but_does_not_block_cache_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    cache = tmp_path / "knowledge_cache" / "st" / "STM32F103RCT6"
    cache.mkdir(parents=True)
    datasheet = cache / "datasheet.md"
    datasheet.write_text("changed cache notes", encoding="utf-8")
    svd = cache / "device.svd"
    svd.write_text("<device/>", encoding="utf-8")
    linker = cache / "linker.ld"
    linker.write_text("MEMORY {}", encoding="utf-8")
    (cache / "manifest.json").write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "documents": [
                    {"kind": "datasheet", "local_path": "datasheet.md", "sha256": "0" * 64},
                    {"kind": "svd", "local_path": "device.svd"},
                    {"kind": "linker", "local_path": "linker.ld"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = locate_docs(project, chip="STM32F103RCT6")

    assert report["ok"] is True
    mismatch = next(item for item in report["diagnostics"] if item["code"] == "hash_mismatch")
    assert mismatch["blocks"] is False


def test_prepare_mcu_blocks_hash_mismatch_before_context_generation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo_chip_dir = tmp_path / "mcu-docs" / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    docs_dir = repo_chip_dir / "documents"
    docs_dir.mkdir(parents=True)
    datasheet = docs_dir / "datasheet.md"
    datasheet.write_text("changed local notes", encoding="utf-8")
    svd = repo_chip_dir / "svd" / "device.svd"
    svd.parent.mkdir()
    svd.write_text("<device/>", encoding="utf-8")
    linker = repo_chip_dir / "linker" / "linker.ld"
    linker.parent.mkdir()
    linker.write_text("MEMORY {}", encoding="utf-8")
    (repo_chip_dir / "manifest.json").write_text(
        json.dumps(
            {
                "chip": "STM32F103RCT6",
                "documents": [
                    {
                        "kind": "datasheet",
                        "local_path": "documents/datasheet.md",
                        "local_sha256": "0" * 64,
                    },
                    {"kind": "svd", "local_path": "svd/device.svd"},
                    {"kind": "linker", "local_path": "linker/linker.ld"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = prepare_mcu(
        project_path=project,
        output_path=tmp_path / "context.json",
        chip="STM32F103RCT6",
        doc_repo_paths=[tmp_path / "mcu-docs"],
    )

    assert report["ok"] is False
    assert report["status"] == "doc_repo_diagnostics_failed"
    assert report["diagnostics"][0]["code"] == "hash_mismatch"


def test_locate_docs_blocks_alias_conflict(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = tmp_path / "mcu-docs"
    for chip in ("STM32F103RCT6", "STM32F103RBT6"):
        chip_dir = repo / "vendors" / "st" / "stm32f1" / chip
        docs_dir = chip_dir / "documents"
        docs_dir.mkdir(parents=True)
        datasheet = docs_dir / "datasheet.md"
        datasheet.write_text(f"{chip} datasheet notes", encoding="utf-8")
        (chip_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "chip": chip,
                    "aliases": ["STM32F103RC"],
                    "documents": [
                        {"kind": "datasheet", "local_path": "documents/datasheet.md"},
                    ],
                }
            ),
            encoding="utf-8",
        )

    report = locate_docs(project, chip="STM32F103RC", doc_repo_paths=[repo])

    assert report["ok"] is False
    diagnostics = {item["code"]: item for item in report["diagnostics"]}
    assert diagnostics["chip_alias_conflict"]["blocks"] is True
    assert diagnostics["chip_alias_conflict"]["requested_chip"] == "STM32F103RC"
