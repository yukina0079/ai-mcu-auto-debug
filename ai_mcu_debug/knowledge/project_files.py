from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_linker_memory(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    memory_match = re.search(r"MEMORY\s*\{(?P<body>.*?)\}", text, flags=re.DOTALL)
    if not memory_match:
        return []
    regions: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<name>\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*(?P<origin>[^,]+),\s*LENGTH\s*=\s*(?P<length>[^\s]+)",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(memory_match.group("body")):
        origin = _parse_int(match.group("origin"))
        length = _parse_length(match.group("length"))
        regions.append(
            {
                "name": match.group("name"),
                "origin": origin,
                "length": length,
                "end": origin + length,
                "source": str(path),
            }
        )
    return regions


def parse_startup_vectors(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"vector_table.*?=\s*\{(?P<body>.*?)\};", text, flags=re.DOTALL)
    if not match:
        return []
    vectors: list[dict[str, Any]] = []
    for index, raw_line in enumerate(match.group("body").splitlines()):
        line = raw_line.split("//", 1)[0].strip().rstrip(",")
        if not line:
            continue
        vectors.append({"index": len(vectors), "symbol": line, "source_line": index + 1, "source": str(path)})
    return vectors


def load_text_document(path: Path, kind: str) -> dict[str, Any]:
    text = _load_pdf_text(path) if path.suffix.lower() == ".pdf" else path.read_text(encoding="utf-8", errors="replace")
    return {
        "kind": kind,
        "path": str(path),
        "title": path.stem,
        "text": text,
    }


def _parse_int(value: str) -> int:
    return int(value.strip().replace("#", "0x"), 0)


def _parse_length(value: str) -> int:
    raw = value.strip().upper()
    multiplier = 1
    if raw.endswith("K"):
        multiplier = 1024
        raw = raw[:-1]
    elif raw.endswith("M"):
        multiplier = 1024 * 1024
        raw = raw[:-1]
    return int(raw, 0) * multiplier


def _load_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return "PDF text extraction unavailable. Install pypdf or provide a text/Markdown excerpt for this document."

    reader = PdfReader(str(path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n--- page {index} ---\n{text}")
    return "\n".join(pages)
