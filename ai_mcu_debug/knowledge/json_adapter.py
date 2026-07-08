from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_mcu_debug.interfaces import KnowledgeAdapter
from ai_mcu_debug.knowledge.vector_index import LocalSimilarityIndex


class JsonKnowledgeAdapter(KnowledgeAdapter):
    def __init__(self, context_path: Path) -> None:
        self.context_path = context_path
        self.context = json.loads(context_path.read_text(encoding="utf-8"))
        self._similarity = LocalSimilarityIndex.from_context(self.context)

    def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        query_terms = _terms(query)
        hits: list[dict[str, object]] = []
        for register in _registers(self.context):
            text = _register_text(register)
            score = _score(text, query_terms)
            if score:
                hits.append({"score": score, "kind": "register", "reference": _register_reference(register), "item": register})
        for chunk in self.context.get("document_chunks", []):
            score = _score(chunk.get("text", ""), query_terms)
            if score:
                hits.append({"score": score, "kind": "document", "reference": _document_reference(chunk), "item": chunk})
        for risk in self.context.get("errata_risks", []):
            score = _score(_errata_text(risk), query_terms)
            if score:
                hits.append({"score": score, "kind": "errata_risk", "reference": _errata_reference(risk), "item": risk})
        return sorted(hits, key=lambda item: item["score"], reverse=True)[:limit]

    def vector_search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        return self._similarity.search(query, limit=limit)

    def explain_register(self, identifier: str) -> dict[str, object]:
        register = self._find_register(identifier)
        if not register:
            return {
                "ok": False,
                "uncertain": True,
                "reason": "register_not_found_in_mcu_context",
                "identifier": identifier,
            }
        return {
            "ok": True,
            "uncertain": False,
            "register": register,
            "reference": _register_reference(register),
            "related_errata_risks": self._related_errata_for_register(register),
        }

    def validate_register_write(self, identifier: str, value: int) -> dict[str, object]:
        register = self._find_register(identifier)
        if not register:
            return {
                "ok": False,
                "allowed": False,
                "requires_approval": True,
                "reason": "unknown_register",
                "identifier": identifier,
                "message": "Register is not present in mcu_context.json; refuse to invent semantics.",
            }
        reasons: list[str] = []
        warnings: list[str] = []
        access = (register.get("access") or "").lower()
        if access in {"read-only", "readonly", "ro"}:
            reasons.append("register_is_read_only")

        field_mask = 0
        read_only_mask = 0
        for field in register.get("fields", []):
            mask = _field_mask(field)
            field_mask |= mask
            field_access = (field.get("access") or access).lower()
            if field_access in {"read-only", "readonly", "ro"}:
                read_only_mask |= mask
            description = (field.get("description") or "").lower()
            if "write 1 to clear" in description or "w1c" in description:
                warnings.append(f"field_{field.get('name')}_may_be_write_one_to_clear")

        size = int(register.get("size") or 32)
        size_mask = (1 << size) - 1 if size < 64 else (1 << 64) - 1
        if value & ~size_mask:
            reasons.append("value_exceeds_register_size")
        if field_mask and (value & size_mask) & ~field_mask:
            reasons.append("reserved_bits_set")
        if read_only_mask and value & read_only_mask:
            reasons.append("read_only_field_bits_set")

        return {
            "ok": not reasons,
            "allowed": not reasons,
            "requires_approval": bool(reasons or warnings or self._related_write_errata(register)),
            "reason": reasons or ["write_matches_known_register_fields"],
            "warnings": warnings + _errata_warning_messages(self._related_write_errata(register)),
            "register": register["qualified_name"],
            "value": f"0x{value:X}",
            "reference": _register_reference(register),
            "related_errata_risks": self._related_write_errata(register),
        }

    def validate_address_write(self, address: int, length: int) -> dict[str, object]:
        end = address + max(0, length)
        hits = []
        for rule in self.context.get("risk_rules", {}).get("dangerous_address_ranges", []):
            if address < rule["end"] and end > rule["start"]:
                hits.append(rule)
        if hits:
            return {
                "ok": False,
                "allowed": False,
                "requires_approval": True,
                "reason": "dangerous_address_range",
                "address": f"0x{address:X}",
                "length": length,
                "matches": hits,
            }
        region = self._memory_region_for(address, max(1, length))
        if region and str(region.get("name", "")).upper() == "RAM":
            return {
                "ok": True,
                "allowed": True,
                "requires_approval": False,
                "reason": "known_ram_region",
                "address": f"0x{address:X}",
                "length": length,
                "region": region,
            }
        register = self._find_register(f"0x{address:08X}")
        if register:
            size_bytes = max(1, int(register.get("size") or 32) // 8)
            if length <= size_bytes:
                return {
                    "ok": True,
                    "allowed": True,
                    "requires_approval": False,
                    "reason": "known_memory_mapped_register",
                    "address": f"0x{address:X}",
                    "length": length,
                    "register": register["qualified_name"],
                    "reference": _register_reference(register),
                }
        return {
            "ok": False,
            "allowed": False,
            "requires_approval": True,
            "reason": "unknown_or_unapproved_address",
            "address": f"0x{address:X}",
            "length": length,
        }

    def _memory_region_for(self, address: int, length: int) -> dict[str, Any] | None:
        end = address + max(0, length)
        for region in self.context.get("memory_regions", []):
            if int(region["origin"]) <= address and end <= int(region["end"]):
                return region
        return None

    def _find_register(self, identifier: str) -> dict[str, Any] | None:
        normalized = identifier.upper()
        if normalized.startswith("0X"):
            normalized = f"0x{int(identifier, 0):08X}"
        return self.context.get("register_index", {}).get(normalized)

    def _related_errata_for_register(self, register: dict[str, Any]) -> list[dict[str, Any]]:
        qualified = register["qualified_name"]
        peripheral = qualified.split(".", 1)[0]
        related: list[dict[str, Any]] = []
        for risk in self.context.get("errata_risks", []):
            subjects = risk.get("subjects", {})
            if qualified in subjects.get("registers", []) or peripheral in subjects.get("peripherals", []):
                related.append(risk)
        return related

    def _related_write_errata(self, register: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            risk
            for risk in self._related_errata_for_register(register)
            if any(operation in risk.get("guard", {}).get("operations", []) for operation in ("write-register", "write-memory"))
        ]


def _registers(context: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for peripheral in context.get("device", {}).get("peripherals", []):
        items.extend(peripheral.get("registers", []))
    return items


def _terms(query: str) -> list[str]:
    return [term.lower() for term in query.replace(".", " ").replace("_", " ").split() if term.strip()]


def _score(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(lower.count(term) for term in terms)


def _register_text(register: dict[str, Any]) -> str:
    field_text = " ".join(
        f"{field.get('name')} {field.get('description')}" for field in register.get("fields", [])
    )
    return f"{register.get('qualified_name')} {register.get('description')} {field_text}"


def _register_reference(register: dict[str, Any]) -> dict[str, object]:
    return {
        "source": register.get("source"),
        "register": register.get("qualified_name"),
        "address": f"0x{register.get('address', 0):08X}",
    }


def _document_reference(chunk: dict[str, Any]) -> dict[str, object]:
    return {
        "source": chunk.get("path"),
        "kind": chunk.get("kind"),
        "offset": chunk.get("offset"),
    }


def _errata_reference(risk: dict[str, Any]) -> dict[str, object]:
    source = risk.get("source", {})
    return {
        "source": source.get("path"),
        "kind": source.get("kind"),
        "line_start": source.get("line_start"),
        "line_end": source.get("line_end"),
        "risk_id": risk.get("id"),
    }


def _errata_text(risk: dict[str, Any]) -> str:
    return f"{risk.get('title')} {risk.get('category')} {risk.get('severity')} {risk.get('text')} {risk.get('evidence')}"


def _errata_warning_messages(risks: list[dict[str, Any]]) -> list[str]:
    return [f"errata_{risk['id']}_{risk['category']}: {risk['mitigation']}" for risk in risks]


def _field_mask(field: dict[str, Any]) -> int:
    width = int(field.get("bit_width") or 0)
    offset = int(field.get("bit_offset") or 0)
    if width <= 0:
        return 0
    return ((1 << width) - 1) << offset
