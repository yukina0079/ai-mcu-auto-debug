from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


class LocalSimilarityIndex:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.term_frequencies = [_vectorize(item["text"]) for item in items]
        self.idf = _idf(self.term_frequencies)
        self.document_vectors = [_tfidf(vector, self.idf) for vector in self.term_frequencies]
        self.norms = [_norm(vector) for vector in self.document_vectors]

    @classmethod
    def from_context(cls, context: dict[str, Any]) -> "LocalSimilarityIndex":
        return cls(_corpus(context))

    def search(
        self,
        query: str,
        limit: int = 5,
        kinds: set[str] | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        query_vector = _tfidf(_vectorize(query), self.idf)
        query_norm = _norm(query_vector)
        hits: list[dict[str, Any]] = []
        for index, item in enumerate(self.items):
            if kinds and item["kind"] not in kinds:
                continue
            score = _cosine(query_vector, query_norm, self.document_vectors[index], self.norms[index])
            score += _exact_boost(query, item)
            if score > min_score:
                hits.append(
                    {
                        "score": round(score, 6),
                        "kind": item["kind"],
                        "reference": item["reference"],
                        "snippet": item.get("snippet"),
                        "item": item["item"],
                    }
                )
        return sorted(hits, key=lambda hit: (-hit["score"], hit["kind"], str(hit["reference"])))[:limit]


def _corpus(context: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for peripheral in context.get("device", {}).get("peripherals", []):
        for register in peripheral.get("registers", []):
            text = _register_text(register)
            items.append(
                {
                    "id": f"register:{register['qualified_name']}",
                    "kind": "register",
                    "text": text,
                    "reference": _register_reference(register),
                    "snippet": register.get("description"),
                    "item": register,
                }
            )
    for chunk in context.get("document_chunks", []):
        items.append(
            {
                "id": f"document:{chunk.get('path')}:{chunk.get('offset')}",
                "kind": "document",
                "text": chunk.get("text", ""),
                "reference": _document_reference(chunk),
                "snippet": _snippet(chunk.get("text", "")),
                "item": chunk,
            }
        )
    for risk in context.get("errata_risks", context.get("risk_rules", {}).get("errata_risks", [])):
        items.append(
            {
                "id": risk["id"],
                "kind": "errata_risk",
                "text": f"{risk.get('category')} {risk.get('severity')} {risk.get('title')} {risk.get('text')} {' '.join(risk.get('subjects', {}).get('keywords', []))}",
                "reference": _errata_reference(risk),
                "snippet": risk.get("evidence") or risk.get("text"),
                "item": risk,
            }
        )
    return items


def _register_text(register: dict[str, Any]) -> str:
    field_text = " ".join(
        f"{field.get('name')} {field.get('description')}" for field in register.get("fields", [])
    )
    qualified = register.get("qualified_name", "")
    pin_alias = _pin_aliases(qualified, field_text)
    return f"{qualified} {qualified.replace('.', ' ')} {register.get('description')} {field_text} {pin_alias}"


def _pin_aliases(qualified_name: str, text: str) -> str:
    aliases: list[str] = []
    port_match = re.match(r"GPIO([A-Z])\.", qualified_name or "")
    for pin in sorted(set(re.findall(r"(?:pin\s*)?(\d+)", text.lower()))):
        if port_match:
            aliases.append(f"P{port_match.group(1)}{pin}")
            aliases.append(f"port {port_match.group(1)} pin {pin}")
    return " ".join(aliases)


def _tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"0x[0-9a-fA-F]+|[A-Za-z]+[A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?|\d+", text)
    tokens: list[str] = []
    for token in raw_tokens:
        lower = token.lower()
        tokens.append(lower)
        if "." in lower:
            tokens.extend(part for part in lower.split(".") if part)
        port_pin = re.match(r"p([a-z])(\d+)$", lower)
        if port_pin:
            tokens.extend([f"gpio{port_pin.group(1)}", f"pin{port_pin.group(2)}", port_pin.group(2)])
    return [token for token in tokens if len(token) > 1]


def _vectorize(text: str) -> Counter[str]:
    return Counter(_tokenize(text))


def _idf(vectors: list[Counter[str]]) -> dict[str, float]:
    document_count = len(vectors)
    document_frequency: Counter[str] = Counter()
    for vector in vectors:
        document_frequency.update(vector.keys())
    return {
        term: math.log((1 + document_count) / (1 + frequency)) + 1
        for term, frequency in document_frequency.items()
    }


def _tfidf(vector: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    return {term: count * idf.get(term, 1.0) for term, count in vector.items()}


def _norm(vector: dict[str, float]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))


def _cosine(
    left: dict[str, float],
    left_norm: float,
    right: dict[str, float],
    right_norm: float,
) -> float:
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    return dot / (left_norm * right_norm)


def _exact_boost(query: str, item: dict[str, Any]) -> float:
    lower = query.lower()
    reference = item["reference"]
    boost = 0.0
    register = str(reference.get("register", "")).lower()
    address = str(reference.get("address", "")).lower()
    if register and register in lower:
        boost += 3.0
    if address and address in lower:
        boost += 5.0
    if re.search(r"\bp[a-z]\d+\b", lower) and register.endswith((".crl", ".crh")):
        boost += 0.2
    if "led" in lower and register.endswith((".crl", ".crh")):
        boost += 0.2
    if item["kind"] == "errata_risk" and "errata" in lower:
        boost += 1.0
    return boost


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


def _snippet(text: str, length: int = 240) -> str:
    return " ".join(text.split())[:length]
