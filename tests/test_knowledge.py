from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.knowledge import JsonKnowledgeAdapter, build_mcu_context, write_mcu_debug_doc
from ai_mcu_debug.knowledge.compare import compare_debug_report
from ai_mcu_debug.knowledge.project_files import parse_linker_memory, parse_startup_vectors
from ai_mcu_debug.knowledge.svd import parse_svd


ROOT = Path(__file__).resolve().parents[1]
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = ROOT / "examples/firmware/stm32f103_blinky/linker.ld"
STARTUP = ROOT / "examples/firmware/stm32f103_blinky/src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_parse_svd_registers() -> None:
    svd = parse_svd(SVD)

    assert svd["cpu"]["name"] == "CM3"
    gpio = next(item for item in svd["peripherals"] if item["name"] == "GPIOC")
    crh = next(item for item in gpio["registers"] if item["name"] == "CRH")
    assert crh["address"] == 0x40011004
    assert crh["fields"][0]["name"] == "MODE13"


def test_parse_project_files() -> None:
    regions = parse_linker_memory(LINKER)
    vectors = parse_startup_vectors(STARTUP)

    assert regions[0]["name"] == "FLASH"
    assert regions[0]["origin"] == 0x08000000
    assert any("Reset_Handler" in vector["symbol"] for vector in vectors)


def test_context_query_and_write_guards(tmp_path: Path) -> None:
    context_path = tmp_path / "mcu_context.json"
    build_mcu_context(
        chip="STM32F103C8",
        svd_path=SVD,
        output_path=context_path,
        linker_path=LINKER,
        startup_path=STARTUP,
        documents=[("datasheet", DATASHEET), ("errata", ERRATA)],
        board="test_board",
    )
    adapter = JsonKnowledgeAdapter(context_path)

    hits = adapter.search("GPIOC pin 13", limit=3)
    vector_hits = adapter.vector_search("GPIOC LED pin", limit=3)
    assert hits
    assert vector_hits
    assert adapter.context["errata_risks"]
    assert not any(risk["source"]["path"] == str(DATASHEET) for risk in adapter.context["errata_risks"])
    assert any(risk["category"] == "revision_scope" for risk in adapter.context["errata_risks"])
    assert any(risk["category"] == "documentation_mismatch" for risk in adapter.context["errata_risks"])
    assert adapter.explain_register("0x40011004")["ok"] is True
    assert adapter.validate_register_write("GPIOC.CRH", 0x00200000)["ok"] is True
    assert adapter.validate_register_write("GPIOC.CRH", 0x00000001)["ok"] is False
    assert adapter.validate_register_write("GPIOC.IDR", 0x2000)["reason"] == ["register_is_read_only", "read_only_field_bits_set"]
    assert adapter.validate_address_write(0x08000000, 4)["ok"] is False
    assert adapter.validate_address_write(0x20000000, 4)["ok"] is True
    assert adapter.validate_address_write(0x50000000, 4)["reason"] == "unknown_or_unapproved_address"


def test_vector_search_exact_address_prefers_register(tmp_path: Path) -> None:
    context_path = tmp_path / "mcu_context.json"
    build_mcu_context(chip="STM32F103C8", svd_path=SVD, output_path=context_path)
    adapter = JsonKnowledgeAdapter(context_path)

    hits = adapter.vector_search("0x40011004", limit=1)

    assert hits[0]["kind"] == "register"
    assert hits[0]["reference"]["register"] == "GPIOC.CRH"


def test_vector_search_pc13_hits_gpio_context(tmp_path: Path) -> None:
    context_path = tmp_path / "mcu_context.json"
    build_mcu_context(
        chip="STM32F103C8",
        svd_path=SVD,
        output_path=context_path,
        documents=[("datasheet", DATASHEET)],
    )
    adapter = JsonKnowledgeAdapter(context_path)

    hits = adapter.vector_search("LED PC13", limit=3)

    assert any(hit["kind"] == "register" and hit["reference"]["register"] == "GPIOC.CRH" for hit in hits)


def test_write_mcu_debug_doc(tmp_path: Path) -> None:
    context_path = tmp_path / "mcu_context.json"
    output_path = tmp_path / "debug_doc.md"
    build_mcu_context(
        chip="STM32F103C8",
        svd_path=SVD,
        output_path=context_path,
        linker_path=LINKER,
        startup_path=STARTUP,
    )

    report = write_mcu_debug_doc(context_path, output_path)

    assert report["ok"] is True
    assert "STM32F103C8 MCU 调试记录文档" in output_path.read_text(encoding="utf-8")


def test_compare_debug_report_to_context(tmp_path: Path) -> None:
    context_path = tmp_path / "mcu_context.json"
    report_path = tmp_path / "debug_report.json"
    build_mcu_context(
        chip="STM32F103C8",
        svd_path=SVD,
        output_path=context_path,
        linker_path=LINKER,
        startup_path=STARTUP,
        documents=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )
    report_path.write_text(
        """{
  "task": "sample",
  "registers": {
    "pc": "0x08000040",
    "sp": "0x20001000",
    "xpsr": "0x01000000"
  },
  "memory": [
    {"address": "0x20000000", "length": 4, "data_hex": "01020304"}
  ],
  "failure_analysis": {
    "probable_causes": ["debug_probe_open_failed"],
    "next_actions": ["Check SWD debug reset"]
  }
}""",
        encoding="utf-8",
    )

    result = compare_debug_report(context_path, report_path)

    assert result["ok"] is True
    names = [item["name"] for item in result["comparisons"]]
    assert "pc_location" in names
    assert "memory_read_region" in names
    assert "failure_related_knowledge" in names
    assert result["registers"]
    assert result["memory"]


def test_compare_debug_report_detects_boundary_crossing(tmp_path: Path) -> None:
    context_path = tmp_path / "mcu_context.json"
    report_path = tmp_path / "debug_report.json"
    build_mcu_context(
        chip="STM32F103C8",
        svd_path=SVD,
        output_path=context_path,
        linker_path=LINKER,
        documents=[("datasheet", DATASHEET)],
    )
    report_path.write_text(
        """{
  "memory": [
    {"address": "0x20004FFC", "length": 16, "data_hex": "00000000000000000000000000000000"}
  ]
}""",
        encoding="utf-8",
    )

    result = compare_debug_report(context_path, report_path)

    memory_region = next(item for item in result["comparisons"] if item["name"] == "memory_read_region")
    assert memory_region["ok"] is False
