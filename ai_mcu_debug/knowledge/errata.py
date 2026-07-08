from __future__ import annotations

import hashlib
import re
from typing import Any


ERRATA_CATEGORIES = {
    "revision_scope": ("part number", "revision", "revision id", "device marking", "silicon revision"),
    "documentation_mismatch": (
        "behavior differs",
        "differs from",
        "not as documented",
        "reference manual",
        "register documentation",
        "uncertain",
        "workaround",
    ),
    "write_hazard": ("write", "program", "erase", "option byte", "flash", "corrupt", "lock"),
    "flag_semantics": ("write 1 to clear", "w1c", "not cleared", "flag", "overrun"),
    "debug_connection": ("debug", "swd", "jtag", "halt", "reset", "boot", "low-power"),
    "clock_timing": ("clock", "pll", "oscillator", "timing", "frequency"),
    "interrupt_dma": ("interrupt", "irq", "dma", "event", "missed", "lost"),
}

CRITICAL_WORDS = ("corrupt", "erase", "lock", "permanent", "data loss")
WARNING_WORDS = ("fail", "wrong", "lost", "hang", "stuck", "differs", "workaround", "uncertain")


def extract_errata_risks(chip: str, documents: list[dict[str, Any]], svd: dict[str, Any]) -> list[dict[str, Any]]:
    subjects = _build_subject_index(svd)
    risks: list[dict[str, Any]] = []
    for doc in documents:
        if not _is_errata_doc(doc):
            continue
        for entry in _iter_evidence_entries(doc):
            risk = _entry_to_risk(chip, doc, entry, subjects)
            if risk:
                risks.append(risk)
    return sorted(risks, key=lambda item: item["id"])


def match_errata_risks_to_text(text: str, risks: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    lower = text.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for risk in risks:
        score = 0
        for keyword in risk.get("subjects", {}).get("keywords", []):
            if keyword.lower() in lower:
                score += 2
        if risk.get("category", "").replace("_", " ") in lower:
            score += 3
        for register in risk.get("subjects", {}).get("registers", []):
            if register.lower() in lower:
                score += 5
        if score:
            scored.append((score, risk))
    return [risk for _, risk in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def _is_errata_doc(doc: dict[str, Any]) -> bool:
    text = " ".join(str(doc.get(key, "")) for key in ("kind", "path", "title")).lower()
    return "errata" in text


def _iter_evidence_entries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    offset = 0
    for line_number, raw_line in enumerate(doc.get("text", "").splitlines(), start=1):
        stripped = raw_line.strip()
        clean = stripped.strip("-* \t")
        if clean and not clean.startswith("#"):
            entries.append(
                {
                    "text": clean.rstrip("."),
                    "line_start": line_number,
                    "line_end": line_number,
                    "offset": offset,
                    "raw": stripped,
                }
            )
        offset += len(raw_line) + 1
    return entries


def _entry_to_risk(
    chip: str,
    doc: dict[str, Any],
    entry: dict[str, Any],
    subject_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    text = entry["text"]
    lower = text.lower()
    category = _classify_category(lower)
    if category is None:
        return None
    subjects = _match_subjects(lower, subject_index)
    keywords = _matched_keywords(lower)
    severity = _severity(lower)
    risk_id = _risk_id(doc["path"], entry["offset"], category, subjects, text)
    return {
        "id": risk_id,
        "title": _title_for(category, text),
        "category": category,
        "severity": severity,
        "confidence": "high" if category in {"revision_scope", "documentation_mismatch"} else "medium",
        "applies_to": {"chip": chip, "part_number": None, "revision": None},
        "subjects": {
            "peripherals": subjects["peripherals"],
            "registers": subjects["registers"],
            "fields": subjects["fields"],
            "addresses": subjects["addresses"],
            "keywords": keywords,
        },
        "trigger": _trigger_for(category),
        "impact": _impact_for(category),
        "mitigation": _mitigation_for(category),
        "actions": _actions_for(category),
        "guard": {"operations": _guard_operations_for(category), "effect": "warn"},
        "source": {
            "kind": doc["kind"],
            "path": doc["path"],
            "title": doc["title"],
            "offset": entry["offset"],
            "line_start": entry["line_start"],
            "line_end": entry["line_end"],
        },
        "evidence": entry["raw"],
        "text": text,
    }


def _build_subject_index(svd: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for peripheral in svd.get("peripherals", []):
        pname = peripheral["name"]
        index[pname.lower()] = {"kind": "peripheral", "name": pname}
        for register in peripheral.get("registers", []):
            rname = register["qualified_name"]
            index[rname.lower()] = {"kind": "register", "name": rname, "address": register["address"]}
            index[register["name"].lower()] = {"kind": "register", "name": rname, "address": register["address"]}
            index[f"0x{register['address']:08x}"] = {
                "kind": "register",
                "name": rname,
                "address": register["address"],
            }
            for field in register.get("fields", []):
                if field.get("name"):
                    index[field["name"].lower()] = {"kind": "field", "name": field["name"], "register": rname}
    return index


def _match_subjects(text: str, index: dict[str, dict[str, Any]]) -> dict[str, list[Any]]:
    subjects = {"peripherals": [], "registers": [], "fields": [], "addresses": []}
    for token, item in index.items():
        if not _contains_subject(text, token):
            continue
        if item["kind"] == "peripheral":
            subjects["peripherals"].append(item["name"])
        elif item["kind"] == "register":
            subjects["registers"].append(item["name"])
            if "address" in item:
                subjects["addresses"].append(f"0x{item['address']:08X}")
        elif item["kind"] == "field":
            subjects["fields"].append(item["name"])
            subjects["registers"].append(item["register"])
    return {key: sorted(set(value)) for key, value in subjects.items()}


def _contains_subject(text: str, token: str) -> bool:
    if token.startswith("0x"):
        return token in text
    pattern = rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])"
    return re.search(pattern, text) is not None


def _classify_category(text: str) -> str | None:
    if any(keyword in text for keyword in ERRATA_CATEGORIES["documentation_mismatch"]):
        return "documentation_mismatch"
    for category, keywords in ERRATA_CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            return category
    return None


def _matched_keywords(text: str) -> list[str]:
    matches: list[str] = []
    for keywords in ERRATA_CATEGORIES.values():
        matches.extend(keyword for keyword in keywords if keyword in text)
    return sorted(set(matches))


def _severity(text: str) -> str:
    if any(word in text for word in CRITICAL_WORDS):
        return "critical"
    if any(word in text for word in WARNING_WORDS):
        return "warning"
    return "advisory"


def _risk_id(path: str, offset: int, category: str, subjects: dict[str, list[Any]], text: str) -> str:
    payload = f"{path}|{offset}|{category}|{subjects}|{text}".encode("utf-8")
    return f"errata:{hashlib.sha1(payload).hexdigest()[:10]}"


def _title_for(category: str, text: str) -> str:
    if category == "revision_scope":
        return "Verify exact part number and revision"
    if category == "documentation_mismatch":
        return "Mark conclusion uncertain when behavior differs from documentation"
    words = text.split()
    return " ".join(words[:10])


def _trigger_for(category: str) -> str:
    if category == "revision_scope":
        return "Using errata evidence for this chip."
    if category == "documentation_mismatch":
        return "Observed behavior differs from documented register or peripheral behavior."
    return "Debug action touches a subject mentioned in errata evidence."


def _impact_for(category: str) -> str:
    return {
        "revision_scope": "Errata may not apply to the actual silicon revision.",
        "documentation_mismatch": "AI conclusion may be wrong if it trusts only nominal documentation.",
        "write_hazard": "Write operation may corrupt configuration or data.",
        "flag_semantics": "Flag handling may clear or preserve status bits unexpectedly.",
        "debug_connection": "Debug halt/reset behavior may differ from expectation.",
        "clock_timing": "Clock or timing setup may be unstable on affected revisions.",
        "interrupt_dma": "Interrupt, event, or DMA behavior may lose data or miss events.",
    }.get(category, "Errata may affect this debug conclusion.")


def _mitigation_for(category: str) -> str:
    return {
        "revision_scope": "Check device marking/revision ID against the vendor errata.",
        "documentation_mismatch": "Mark the conclusion as uncertain and cite errata evidence.",
        "write_hazard": "Require approval before writes and verify backup/recovery path.",
        "flag_semantics": "Read-modify-write carefully and confirm flag clearing semantics.",
        "debug_connection": "Check debug probe, reset mode, and low-power/debug configuration.",
        "clock_timing": "Confirm clock source, PLL state, and workaround before changing clocks.",
        "interrupt_dma": "Check interrupt/DMA flags and errata workaround before diagnosing.",
    }.get(category, "Cite errata evidence and require confirmation.")


def _actions_for(category: str) -> list[str]:
    return {
        "revision_scope": ["verify_part_revision", "cite_source"],
        "documentation_mismatch": ["mark_uncertain", "require_confirmation", "cite_source"],
        "write_hazard": ["require_approval", "cite_source"],
        "flag_semantics": ["warn_before_write", "cite_source"],
    }.get(category, ["warn", "cite_source"])


def _guard_operations_for(category: str) -> list[str]:
    if category in {"write_hazard", "flag_semantics"}:
        return ["write-register", "write-memory"]
    if category == "debug_connection":
        return ["reset", "halt", "resume", "step"]
    return []
