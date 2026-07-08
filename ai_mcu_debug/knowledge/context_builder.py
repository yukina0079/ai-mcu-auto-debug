from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errata import extract_errata_risks
from .project_files import load_text_document, parse_linker_memory, parse_startup_vectors
from .svd import parse_svd


def build_mcu_context(
    chip: str,
    svd_path: Path,
    output_path: Path,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    documents: list[tuple[str, Path]] | None = None,
    board: str | None = None,
    package_name: str | None = None,
) -> dict[str, Any]:
    svd = parse_svd(svd_path)
    memory_regions = parse_linker_memory(linker_path) if linker_path else []
    interrupt_vectors = parse_startup_vectors(startup_path) if startup_path else []
    docs = [load_text_document(path, kind) for kind, path in documents or []]
    register_index = _build_register_index(svd)
    errata_risks = extract_errata_risks(chip, docs, svd)

    context = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chip": chip,
        "board": board,
        "package": package_name,
        "sources": {
            "svd": str(svd_path),
            "linker": str(linker_path) if linker_path else None,
            "startup": str(startup_path) if startup_path else None,
            "documents": [{"kind": kind, "path": str(path)} for kind, path in documents or []],
        },
        "device": svd,
        "memory_regions": memory_regions,
        "interrupt_vectors": interrupt_vectors,
        "register_index": register_index,
        "document_chunks": _chunk_documents(docs),
        "datasheet_facts": _extract_datasheet_facts(docs),
        "errata_risks": errata_risks,
        "risk_rules": _build_risk_rules(memory_regions),
        "debug_notes": _build_debug_notes(chip, svd, memory_regions, interrupt_vectors),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(context, file, indent=2, ensure_ascii=False)
    return context


def write_mcu_debug_doc(context_path: Path, output_path: Path) -> dict[str, Any]:
    context = json.loads(context_path.read_text(encoding="utf-8"))
    lines = [
        f"# {context['chip']} MCU 调试记录文档",
        "",
        "## 来源",
        "",
        f"- SVD: `{context['sources'].get('svd')}`",
        f"- Linker: `{context['sources'].get('linker')}`",
        f"- Startup: `{context['sources'].get('startup')}`",
        "",
        "## Memory Map",
        "",
    ]
    for region in context.get("memory_regions", []):
        lines.append(
            f"- {region['name']}: 0x{region['origin']:08X} - 0x{region['end'] - 1:08X} ({region['length']} bytes)"
        )
    lines.extend(["", "## 外设寄存器", ""])
    for peripheral in context["device"].get("peripherals", []):
        lines.append(f"### {peripheral['name']} @ 0x{peripheral['base_address']:08X}")
        if peripheral.get("description"):
            lines.append(peripheral["description"])
        for register in peripheral.get("registers", []):
            lines.append(
                f"- {register['qualified_name']} @ 0x{register['address']:08X}, access={register.get('access')}, reset=0x{register.get('reset_value', 0):X}"
            )
        lines.append("")
    lines.extend(["## 调试注意事项", ""])
    for note in context.get("debug_notes", []):
        lines.append(f"- {note}")
    errata_risks = context.get("errata_risks", [])
    if errata_risks:
        lines.extend(["", "## Errata 风险清单", ""])
        for risk in errata_risks:
            source = risk.get("source", {})
            lines.append(
                f"- `{risk['id']}` [{risk['severity']}] {risk['category']}: {risk['title']} "
                f"({source.get('path')}:{source.get('line_start')})"
            )
            lines.append(f"  - Evidence: {risk['evidence']}")
            lines.append(f"  - Mitigation: {risk['mitigation']}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "output": str(output_path)}


def _build_register_index(svd: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for peripheral in svd.get("peripherals", []):
        for register in peripheral.get("registers", []):
            address_key = f"0x{register['address']:08X}"
            index[register["qualified_name"].upper()] = register
            index[address_key] = register
    return index


def _chunk_documents(documents: list[dict[str, Any]], chunk_size: int = 1200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for doc in documents:
        text = doc["text"]
        for offset in range(0, len(text), chunk_size):
            chunks.append(
                {
                    "kind": doc["kind"],
                    "path": doc["path"],
                    "title": doc["title"],
                    "offset": offset,
                    "text": text[offset : offset + chunk_size],
                }
            )
    return chunks


def _build_risk_rules(memory_regions: list[dict[str, Any]]) -> dict[str, Any]:
    dangerous_ranges = []
    for region in memory_regions:
        if region["name"].upper() in {"FLASH", "OPTION", "OPTION_BYTES"}:
            dangerous_ranges.append(
                {
                    "name": region["name"],
                    "start": region["origin"],
                    "end": region["end"],
                    "reason": "Non-volatile memory write can erase or corrupt firmware/configuration.",
                }
            )
    return {
        "dangerous_address_ranges": dangerous_ranges,
        "errata_policy": "warn_and_cite",
        "default_write_policy": "deny_unknown_registers",
    }


def _extract_datasheet_facts(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for doc in documents:
        if doc["kind"].lower() not in {"datasheet", "reference", "reference_manual", "board"}:
            continue
        offset = 0
        for line_number, raw_line in enumerate(doc["text"].splitlines(), start=1):
            line = raw_line.strip(" -*\t")
            lower = line.lower()
            fact_type = None
            if "cortex-m" in lower:
                fact_type = "cpu_core"
            elif "flash" in lower and "0x" in lower:
                fact_type = "flash_base"
            elif ("sram" in lower or "ram" in lower) and "0x" in lower:
                fact_type = "ram_base"
            elif "gpio" in lower or "led" in lower or "pin" in lower:
                fact_type = "board_pin"
            if fact_type:
                facts.append(
                    {
                        "kind": fact_type,
                        "text": line,
                        "source": {
                            "kind": doc["kind"],
                            "path": doc["path"],
                            "title": doc["title"],
                            "offset": offset,
                            "line_start": line_number,
                            "line_end": line_number,
                        },
                    }
                )
            offset += len(raw_line) + 1
    return facts


def _build_debug_notes(
    chip: str,
    svd: dict[str, Any],
    memory_regions: list[dict[str, Any]],
    interrupt_vectors: list[dict[str, Any]],
) -> list[str]:
    notes = [f"Use mcu_context.json as evidence before explaining or writing registers for {chip}."]
    if svd.get("cpu", {}).get("name"):
        notes.append(f"CPU core from SVD: {svd['cpu']['name']}.")
    if memory_regions:
        notes.append("Memory ranges are taken from linker script and should be checked before raw memory writes.")
    if interrupt_vectors:
        notes.append("Interrupt vector symbols are taken from startup file and can guide reset/HardFault debugging.")
    notes.append("Do not invent register fields. If a register or field is missing from SVD, report uncertainty.")
    return notes
