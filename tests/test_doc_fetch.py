from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ai_mcu_debug.knowledge.doc_fetch import discover_docs, fetch_docs, ingest_docs


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER_RCT6 = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_discover_docs_returns_official_stm32f103rct6_candidates() -> None:
    report = discover_docs("STM32F103RCT6")

    assert report["ok"] is True
    candidates = {item["kind"]: item for item in report["candidates"]}
    assert candidates["datasheet"]["url"].endswith("/stm32f103rc.pdf")
    assert "rm0008" in candidates["reference_manual"]["url"]
    assert "es0340" in candidates["errata"]["url"]
    assert candidates["cmsis_pack"]["kind"] == "cmsis_pack"
    assert "cmsis_pack=" in " ".join(report["fetch_urls"])


def test_discover_docs_reports_unsupported_chip_without_guessing() -> None:
    report = discover_docs("UNKNOWN123")

    assert report["ok"] is False
    assert report["status"] == "unsupported_chip"
    assert report["candidates"] == []
    missing = {item["kind"] for item in report["missing"]}
    assert {"datasheet_or_reference", "svd"} <= missing
    assert any(action.startswith("Ask the user") for action in report["next_actions"])


def test_fetch_docs_downloads_urls_and_writes_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"

    report = fetch_docs(
        chip="STM32F103RCT6",
        urls=[("datasheet", DATASHEET.as_uri())],
        manifest_path=manifest,
    )

    assert report["ok"] is True
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["chip"] == "STM32F103RCT6"
    assert data["documents"][0]["kind"] == "datasheet"
    assert data["documents"][0]["sha256"]
    assert Path(data["documents"][0]["local_path"]).exists()


def test_fetch_docs_accepts_plain_local_file_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    local_doc = tmp_path / "datasheet.md"
    local_doc.write_text("local user provided datasheet", encoding="utf-8")

    report = fetch_docs(
        chip="STM32F103RCT6",
        urls=[("datasheet", str(local_doc))],
        manifest_path=manifest,
    )

    assert report["ok"] is True
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["documents"][0]["source_domain"] == "local_file"
    assert data["documents"][0]["trust_level"] == "explicit"
    assert Path(data["documents"][0]["local_path"]).read_text(encoding="utf-8") == "local user provided datasheet"


def test_fetch_docs_extracts_matching_svd_from_cmsis_pack(tmp_path: Path) -> None:
    pack = tmp_path / "Keil.STM32F1xx_DFP.test.pack"
    with zipfile.ZipFile(pack, "w") as archive:
        archive.writestr("CMSIS/SVD/STM32F101xx.svd", "<device><name>STM32F101xx</name></device>")
        archive.writestr("CMSIS/SVD/STM32F103xC.svd", "<device><name>STM32F103xC</name></device>")
    manifest = tmp_path / "manifest.json"

    report = fetch_docs(
        chip="STM32F103RCT6",
        urls=[("cmsis_pack", pack.as_uri())],
        manifest_path=manifest,
    )

    assert report["ok"] is True
    data = json.loads(manifest.read_text(encoding="utf-8"))
    svd_entries = [item for item in data["documents"] if item["kind"] == "svd"]
    assert len(svd_entries) == 1
    assert svd_entries[0]["trust_level"] == "cmsis_pack"
    assert svd_entries[0]["pack_member"].endswith("STM32F103xC.svd")
    assert Path(svd_entries[0]["local_path"]).exists()


def test_ingest_docs_generates_context_from_manifest_and_explicit_project_files(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "chip": "STM32F103RCT6",
                "documents": [
                    {"kind": "datasheet", "local_path": str(DATASHEET)},
                    {"kind": "errata", "local_path": str(ERRATA)},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = ingest_docs(
        manifest_path=manifest,
        output_path=tmp_path / "context.json",
        svd_path=SVD,
        linker_path=LINKER_RCT6,
        startup_path=STARTUP,
        package_name="LQFP64",
    )

    assert report["ok"] is True
    assert report["context_check"]["chip"] == "STM32F103RCT6"
    assert (tmp_path / "context.json").exists()


def test_ingest_docs_reports_missing_required_inputs(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "documents": []}), encoding="utf-8")

    report = ingest_docs(manifest_path=manifest, output_path=tmp_path / "context.json")

    assert report["ok"] is False
    assert report["status"] == "missing_required_document"
    missing = {item["kind"] for item in report["missing"]}
    assert {"chip", "svd", "linker", "datasheet_or_reference"} <= missing
