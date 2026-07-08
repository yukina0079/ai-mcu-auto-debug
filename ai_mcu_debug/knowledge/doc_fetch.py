from __future__ import annotations

import hashlib
import json
import re
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.audit_log import append_audit_event

from .context_builder import build_mcu_context
from .prepare import check_context


TRUSTED_VENDOR_DOMAINS = (
    "st.com",
    "nxp.com",
    "microchip.com",
    "ti.com",
    "renesas.com",
    "infineon.com",
    "nordicsemi.com",
    "silabs.com",
    "arm.com",
    "keil.com",
)


def discover_docs(
    chip: str | None,
    vendor: str | None = None,
    include_cmsis_pack: bool = True,
) -> dict[str, Any]:
    """Return optional deterministic vendor/CMSIS document candidates for a chip.

    This intentionally does not scrape search results and is not part of the
    default AI workflow. If required sources are missing, ask the user for
    official URLs or local files instead of guessing.
    """

    if not chip:
        return {
            "ok": False,
            "status": "missing_chip_identity",
            "chip": chip,
            "candidates": [],
            "missing": [{"kind": "chip", "required": True, "reason": "missing_chip_identity"}],
            "next_actions": ["Provide the exact MCU part number."],
        }

    normalized = _normalize_part(chip)
    selected_vendor = (vendor or _infer_vendor(normalized) or "").lower()
    if selected_vendor in {"st", "stm", "stmicro", "stmicroelectronics"} or normalized.startswith("STM32"):
        return _discover_stm32_docs(normalized, include_cmsis_pack=include_cmsis_pack)

    return {
        "ok": False,
        "status": "unsupported_chip",
        "chip": chip,
        "normalized_chip": normalized,
        "vendor": vendor,
        "candidates": [],
        "missing": [
            {"kind": "datasheet_or_reference", "required": True, "reason": "unsupported_vendor_source_rule"},
            {"kind": "svd", "required": True, "reason": "unsupported_cmsis_pack_rule"},
        ],
        "next_actions": [
            "Ask the user to provide official datasheet/reference manual URLs or local files.",
            "Ask the user to provide a CMSIS-SVD file or trusted CMSIS-Pack URL/file.",
        ],
    }


def fetch_docs(
    chip: str | None,
    urls: list[tuple[str, str]],
    manifest_path: Path,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Download user-provided MCU documents into a cache manifest.

    The caller must provide the files or URLs. This function only performs
    deterministic download/copy, hashing, and manifest recording.
    """

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    documents: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for kind, url in urls:
        try:
            entry = _download_one(kind, url, manifest_path.parent, timeout_s)
            documents.append(entry)
            documents.extend(_expand_downloaded_entry(entry, chip, manifest_path.parent))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            errors.append({"kind": kind, "url": url, "error": str(exc)})

    manifest = {
        "schema_version": 1,
        "chip": chip,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    report = {
        "ok": bool(documents) and not errors,
        "status": "ok" if documents and not errors else "download_incomplete" if documents else "download_failed",
        "manifest": str(manifest_path),
        "documents": documents,
        "errors": errors,
    }
    append_audit_event(
        "fetch_docs",
        args={"chip": chip, "manifest": str(manifest_path), "urls": urls},
        result={
            "status": report["status"],
            "documents": [
                {key: entry.get(key) for key in ("kind", "source_url", "local_path", "sha256", "bytes")}
                for entry in documents
            ],
            "errors": errors,
        },
        ok=bool(report["ok"]),
    )
    return report


def ingest_docs(
    manifest_path: Path,
    output_path: Path,
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    board: str | None = None,
    package_name: str | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = manifest.get("documents", [])
    selected_chip = chip or manifest.get("chip")
    selected_svd = svd_path or _first_local_path(docs, {"svd"})
    selected_linker = linker_path or _first_local_path(docs, {"linker"})
    selected_startup = startup_path or _first_local_path(docs, {"startup"})
    text_docs = [
        (entry["kind"], Path(entry["local_path"]))
        for entry in docs
        if entry.get("kind") in {"datasheet", "reference", "reference_manual", "errata", "board"}
    ]

    missing: list[dict[str, Any]] = []
    if not selected_chip:
        missing.append({"kind": "chip", "required": True, "reason": "missing_chip_identity"})
    if not selected_svd:
        missing.append({"kind": "svd", "required": True, "reason": "missing_svd"})
    if not selected_linker:
        missing.append({"kind": "linker", "required": True, "reason": "missing_linker"})
    if not any(kind in {"datasheet", "reference", "reference_manual"} for kind, _ in text_docs):
        missing.append({"kind": "datasheet_or_reference", "required": True, "reason": "missing_datasheet_or_reference"})
    if missing:
        return {
            "ok": False,
            "status": "missing_required_document",
            "manifest": str(manifest_path),
            "missing": missing,
            "next_actions": _next_actions(missing),
        }

    context = build_mcu_context(
        chip=str(selected_chip),
        svd_path=selected_svd,
        output_path=output_path,
        linker_path=selected_linker,
        startup_path=selected_startup,
        documents=text_docs,
        board=board,
        package_name=package_name,
    )
    check = check_context(output_path)
    return {
        "ok": check["ok"],
        "status": "ok" if check["ok"] else "context_incomplete",
        "manifest": str(manifest_path),
        "output": str(output_path),
        "context_check": check,
        "artifacts": [{"kind": "mcu_context", "path": str(output_path), "registers": len(context["register_index"])}],
    }


def _download_one(kind: str, url: str, output_dir: Path, timeout_s: float) -> dict[str, Any]:
    local_path = Path(url)
    if local_path.exists():
        data = local_path.read_bytes()
        filename = _safe_filename(local_path.name, kind)
        path = output_dir / filename
        path.write_bytes(data)
        return {
            "kind": kind,
            "source_url": str(local_path),
            "source_domain": "local_file",
            "local_path": str(path),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "content_type": None,
            "trust_level": "explicit",
        }

    request = urllib.request.Request(url, headers={"User-Agent": "ai-mcu-debug/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type")
    domain = urllib.parse.urlparse(url).netloc.lower()
    filename = _filename_from_url(url, kind)
    path = output_dir / filename
    path.write_bytes(data)
    return {
        "kind": kind,
        "source_url": url,
        "source_domain": domain,
        "local_path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "content_type": content_type,
        "trust_level": _trust_level_for_download(kind, domain),
    }


def _filename_from_url(url: str, kind: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    return _safe_filename(name, kind)


def _safe_filename(name: str, kind: str) -> str:
    if not name:
        name = f"{kind}.bin"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if "." not in name:
        name = f"{name}.bin"
    return name


def _is_trusted_vendor(domain: str) -> bool:
    return any(domain == trusted or domain.endswith(f".{trusted}") for trusted in TRUSTED_VENDOR_DOMAINS)


def _trust_level_for_download(kind: str, domain: str) -> str:
    normalized_kind = kind.lower()
    if normalized_kind in {"cmsis_pack", "pack", "svd_pack"}:
        return "cmsis_pack" if _is_trusted_vendor(domain) or not domain else "downloaded_pack"
    return "vendor" if _is_trusted_vendor(domain) else "downloaded"


def _expand_downloaded_entry(entry: dict[str, Any], chip: str | None, output_dir: Path) -> list[dict[str, Any]]:
    if entry.get("kind") not in {"cmsis_pack", "pack", "svd_pack"}:
        return []
    pack_path = Path(entry["local_path"])
    if not zipfile.is_zipfile(pack_path):
        return []
    with zipfile.ZipFile(pack_path) as archive:
        svd_members = [name for name in archive.namelist() if name.lower().endswith(".svd")]
        selected = _select_svd_member(svd_members, chip)
        if not selected:
            return []
        data = archive.read(selected)
    svd_dir = output_dir / "svd"
    svd_dir.mkdir(parents=True, exist_ok=True)
    svd_path = svd_dir / _filename_from_url(selected, "svd")
    svd_path.write_bytes(data)
    return [
        {
            "kind": "svd",
            "source_url": entry.get("source_url"),
            "source_domain": entry.get("source_domain"),
            "local_path": str(svd_path),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "content_type": "application/xml",
            "trust_level": "cmsis_pack",
            "derived_from": entry.get("local_path"),
            "pack_member": selected,
        }
    ]


def _select_svd_member(members: list[str], chip: str | None) -> str | None:
    if not members:
        return None
    normalized_chip = _normalize_part(chip or "")
    family = _stm32_family(normalized_chip)
    density = _stm32_density_code(normalized_chip)

    def score(member: str) -> tuple[int, int]:
        name = _normalize_part(Path(member).stem)
        value = 0
        if normalized_chip and normalized_chip in name:
            value += 100
        if family and family in name:
            value += 50
        if density and density in name:
            value += 10
        if "XX" in name:
            value += 1
        return value, -len(member)

    best = max(members, key=score)
    return best if score(best)[0] > 0 or len(members) == 1 else None


def _first_local_path(entries: list[dict[str, Any]], kinds: set[str]) -> Path | None:
    for entry in entries:
        if entry.get("kind") in kinds and entry.get("local_path"):
            return Path(entry["local_path"])
    return None


def _next_actions(missing: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in missing:
        kind = item["kind"]
        if kind == "chip":
            actions.append("Provide --chip or include chip in the manifest.")
        elif kind == "svd":
            actions.append("Fetch or provide a CMSIS-SVD file.")
        elif kind == "linker":
            actions.append("Provide a linker script or memory map.")
        elif kind == "datasheet_or_reference":
            actions.append("Fetch or provide a datasheet/reference manual source.")
    return actions


def _discover_stm32_docs(chip: str, include_cmsis_pack: bool) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    datasheet_slug = _stm32_datasheet_slug(chip)
    if datasheet_slug:
        candidates.append(
            _candidate(
                kind="datasheet",
                url=f"https://www.st.com/resource/en/datasheet/{datasheet_slug}.pdf",
                source="st_resource_rule",
                confidence=0.9,
                evidence=f"STM32 datasheet URLs use the device orderable base `{datasheet_slug}`.",
            )
        )
    else:
        missing.append({"kind": "datasheet", "required": True, "reason": "stm32_datasheet_slug_not_resolved"})

    reference_url = _stm32_reference_manual_url(chip)
    if reference_url:
        candidates.append(
            _candidate(
                kind="reference_manual",
                url=reference_url,
                source="st_family_reference_rule",
                confidence=0.95,
                evidence="STM32F101/F102/F103/F105/F107 share RM0008.",
            )
        )
    else:
        missing.append({"kind": "reference_manual", "required": True, "reason": "stm32_reference_manual_not_mapped"})

    errata_url = _stm32_errata_url(chip)
    if errata_url:
        candidates.append(
            _candidate(
                kind="errata",
                url=errata_url,
                source="st_density_errata_rule",
                confidence=0.85,
                evidence="STM32F103 xC/xD/xE high-density devices use ES0340.",
            )
        )
    else:
        missing.append({"kind": "errata", "required": False, "reason": "stm32_errata_rule_not_mapped"})

    if include_cmsis_pack:
        pack_url = _stm32_cmsis_pack_url(chip)
        if pack_url:
            candidates.append(
                _candidate(
                    kind="cmsis_pack",
                    url=pack_url,
                    source="cmsis_pack_rule",
                    confidence=0.75,
                    evidence="CMSIS-Pack contains vendor SVD files; fetch-docs extracts a matching .svd when present.",
                )
            )
        else:
            missing.append({"kind": "svd", "required": True, "reason": "cmsis_pack_rule_not_mapped"})

    required_missing = [item for item in missing if item["required"]]
    fetch_urls = [f"{item['kind']}={item['url']}" for item in candidates]
    return {
        "ok": not required_missing,
        "status": "ok" if not required_missing else "missing_required_document",
        "chip": chip,
        "normalized_chip": chip,
        "vendor": "st",
        "candidates": candidates,
        "fetch_urls": fetch_urls,
        "missing": missing,
        "next_actions": _discover_next_actions(missing),
    }


def _candidate(kind: str, url: str, source: str, confidence: float, evidence: str) -> dict[str, Any]:
    domain = urllib.parse.urlparse(url).netloc.lower()
    return {
        "kind": kind,
        "url": url,
        "source_domain": domain,
        "trust_level": "cmsis_pack" if "pack" in kind else "vendor" if _is_trusted_vendor(domain) else "candidate",
        "source": source,
        "confidence": confidence,
        "evidence": evidence,
    }


def _discover_next_actions(missing: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in missing:
        if item["required"]:
            actions.append(f"Ask the user to provide {item['kind']} from an official vendor or CMSIS-Pack source.")
        elif item["kind"] == "errata":
            actions.append("If no errata candidate is available, mark errata_missing in the MCU context.")
    return actions


def _infer_vendor(chip: str) -> str | None:
    if chip.startswith("STM32"):
        return "st"
    return None


def _normalize_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _stm32_family(chip: str) -> str | None:
    match = re.match(r"(STM32[A-Z]?\d{3})", chip)
    return match.group(1) if match else None


def _stm32_density_code(chip: str) -> str | None:
    family = _stm32_family(chip)
    if not family or len(chip) <= len(family) + 1:
        return None
    return chip[len(family) + 1]


def _stm32_datasheet_slug(chip: str) -> str | None:
    if not chip.startswith("STM32"):
        return None
    base = chip
    if len(base) >= 12 and re.search(r"[A-Z][0-9]$", base):
        base = base[:-2]
    return base.lower()


def _stm32_reference_manual_url(chip: str) -> str | None:
    if re.match(r"STM32F10[12357]", chip):
        return (
            "https://www.st.com/resource/en/reference_manual/"
            "rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-"
            "advanced-armbased-32bit-mcus-stmicroelectronics.pdf"
        )
    return None


def _stm32_errata_url(chip: str) -> str | None:
    density = _stm32_density_code(chip)
    if chip.startswith("STM32F103") and density in {"C", "D", "E"}:
        return (
            "https://www.st.com/resource/en/errata_sheet/"
            "es0340-stm32f101xcde-stm32f103xcde-device-errata-stmicroelectronics.pdf"
        )
    return None


def _stm32_cmsis_pack_url(chip: str) -> str | None:
    if re.match(r"STM32F10[12357]", chip):
        return "https://www.keil.com/pack/Keil.STM32F1xx_DFP.2.4.1.pack"
    return None
