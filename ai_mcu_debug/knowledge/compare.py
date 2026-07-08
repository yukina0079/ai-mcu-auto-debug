from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .json_adapter import JsonKnowledgeAdapter


def compare_debug_report(context_path: Path, report_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    adapter = JsonKnowledgeAdapter(context_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    debug_report = report.get("debug_report", report)
    comparisons: list[dict[str, Any]] = []

    comparisons.extend(_compare_core_registers(adapter.context, debug_report))
    comparisons.extend(_compare_memory_reads(adapter.context, debug_report))
    comparisons.extend(_compare_known_registers(adapter, debug_report))
    comparisons.extend(_compare_failure_analysis(adapter, debug_report))

    result = {
        "ok": True,
        "context": str(context_path),
        "report": str(report_path),
        "summary": _summary(debug_report, comparisons),
        "comparisons": comparisons,
        "registers": [item for item in comparisons if item.get("group") == "register"],
        "memory": [item for item in comparisons if item.get("group") == "memory"],
        "errors": [item for item in comparisons if item.get("group") == "error"],
        "uncertain": [item for item in comparisons if item.get("uncertain")],
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _compare_core_registers(context: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    registers = {name.lower(): value for name, value in report.get("registers", {}).items()}
    regions = context.get("memory_regions", [])
    items: list[dict[str, Any]] = []
    pc = _parse_int(registers.get("pc"))
    sp = _parse_int(registers.get("sp"))
    xpsr = _parse_int(registers.get("xpsr"))
    if pc is not None:
        items.append(_range_comparison("pc_location", pc, regions, context, expected=("FLASH",), group="register"))
    if sp is not None:
        items.append(_range_comparison("sp_location", sp, regions, context, expected=("RAM",), group="register"))
    if xpsr is not None:
        items.append(
            {
                "name": "xpsr_thumb_bit",
                "group": "register",
                "ok": bool(xpsr & (1 << 24)),
                "value": f"0x{xpsr:X}",
                "evidence": "Cortex-M execution should keep xPSR T bit set.",
            }
        )
    return items


def _compare_memory_reads(context: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    regions = context.get("memory_regions", [])
    items: list[dict[str, Any]] = []
    for memory in report.get("memory", []):
        address = _parse_int(memory.get("address"))
        if address is None:
            continue
        length = int(memory.get("length") or len(memory.get("data_hex", "")) // 2)
        items.append(_range_comparison("memory_read_region", address, regions, context, length=length, group="memory"))
        if address == 0x08000000 and len(memory.get("data_hex", "")) >= 16:
            items.extend(_compare_vector_table(memory, regions, context))
    return items


def _compare_known_registers(adapter: JsonKnowledgeAdapter, report: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, raw_value in report.get("registers", {}).items():
        explanation = adapter.explain_register(name)
        if not explanation.get("ok"):
            continue
        register = explanation["register"]
        value = _parse_int(raw_value)
        reset_value = register.get("reset_value")
        items.append(
            {
                "name": "known_register_value",
                "group": "register",
                "ok": True,
                "register": register["qualified_name"],
                "value": raw_value,
                "reset_value": f"0x{reset_value:X}" if isinstance(reset_value, int) else reset_value,
                "matches_reset": value == reset_value if value is not None and isinstance(reset_value, int) else None,
                "fields": _decode_fields(register, value) if value is not None else [],
                "reference": explanation["reference"],
                "related_errata_risks": explanation.get("related_errata_risks", []),
            }
        )
    return items


def _compare_failure_analysis(adapter: JsonKnowledgeAdapter, report: dict[str, Any]) -> list[dict[str, Any]]:
    failure = report.get("failure_analysis")
    if not failure:
        return []
    query = " ".join(failure.get("probable_causes", []) + failure.get("next_actions", []))
    hits = _filter_failure_hits(adapter.vector_search(query, limit=5))
    return [
        {
            "name": "failure_related_knowledge",
            "group": "error",
            "ok": bool(hits),
            "failure_analysis": failure,
            "related_evidence": [
                {"kind": hit["kind"], "reference": hit["reference"], "score": hit["score"], "snippet": hit.get("snippet")}
                for hit in hits
            ],
            "uncertain": not bool(hits),
        }
    ]


def _filter_failure_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    connection_terms = ("probe", "openocd", "st-link", "j-link", "cmsis-dap", "swd", "jtag")
    filtered: list[dict[str, Any]] = []
    for hit in hits:
        text = f"{hit.get('snippet', '')} {hit.get('reference', {})} {hit.get('item', {})}".lower()
        if any(term in text for term in connection_terms):
            filtered.append(hit)
    return filtered[:3]


def _range_comparison(
    name: str,
    address: int,
    regions: list[dict[str, Any]],
    context: dict[str, Any],
    expected: tuple[str, ...] = (),
    length: int = 1,
    group: str = "memory",
) -> dict[str, Any]:
    region = _region_for(address, regions)
    end_region = _region_for(address + max(length - 1, 0), regions)
    ok = region is not None and end_region == region and (not expected or region["name"].upper() in expected)
    return {
        "name": name,
        "group": group,
        "ok": ok,
        "address": f"0x{address:X}",
        "length": length,
        "region": region,
        "expected": list(expected),
        "uncertain": region is None or end_region is None,
        "evidence": _evidence_for_region(context, region),
    }


def _region_for(address: int, regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    for region in regions:
        if region["origin"] <= address < region["end"]:
            return region
    return None


def _compare_vector_table(memory: dict[str, Any], regions: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    data = bytes.fromhex(memory.get("data_hex", ""))
    initial_sp = int.from_bytes(data[0:4], "little")
    reset_vector = int.from_bytes(data[4:8], "little") & ~1
    return [
        _range_comparison("vector_initial_sp", initial_sp, regions, context, expected=("RAM",), group="memory"),
        _range_comparison("vector_reset_handler", reset_vector, regions, context, expected=("FLASH",), group="memory"),
    ]


def _decode_fields(register: dict[str, Any], value: int) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field in register.get("fields", []):
        width = int(field.get("bit_width") or 0)
        offset = int(field.get("bit_offset") or 0)
        if width <= 0:
            continue
        mask = ((1 << width) - 1) << offset
        fields.append(
            {
                "name": field.get("name"),
                "value": (value & mask) >> offset,
                "bit_offset": offset,
                "bit_width": width,
                "description": field.get("description"),
            }
        )
    return fields


def _evidence_for_region(context: dict[str, Any], region: dict[str, Any] | None) -> dict[str, Any]:
    if region is None:
        return {"kind": "missing", "text": "Address is outside known linker memory regions."}
    evidence = {
        "kind": "memory_region",
        "region": region,
        "source": {"path": region.get("source")},
        "text": "Compared against memory_regions from linker script in mcu_context.json.",
    }
    region_name = region["name"].upper()
    fact_kind = "flash_base" if region_name == "FLASH" else "ram_base" if region_name == "RAM" else None
    facts = [fact for fact in context.get("datasheet_facts", []) if fact.get("kind") == fact_kind]
    if facts:
        evidence["supporting_document"] = {"source": facts[0]["source"], "text": facts[0]["text"]}
    return evidence


def _summary(report: dict[str, Any], comparisons: list[dict[str, Any]]) -> list[str]:
    summary: list[str] = []
    if not report.get("registers"):
        summary.append("no register snapshot available")
    if not report.get("memory"):
        summary.append("no memory snapshot available")
    failing = [item["name"] for item in comparisons if item.get("ok") is False]
    if failing:
        summary.append(f"failed comparisons: {', '.join(failing)}")
    if not summary:
        summary.append("debug report is consistent with available MCU context checks")
    return summary


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None
