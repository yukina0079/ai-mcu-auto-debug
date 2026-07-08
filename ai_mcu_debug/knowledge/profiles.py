from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REFERENCE_KIND_ALIASES = {
    "reference",
    "reference_manual",
    "technical_reference_manual",
    "trm",
    "programming_manual",
    "product_specification",
}


PROFILE_RULES: list[dict[str, Any]] = [
    {
        "id": "stm32f1",
        "vendor": "st",
        "family": "stm32f1",
        "match_prefixes": ["STM32F1", "STM32F10"],
        "required_groups": [
            {"name": "register_map", "any_of": ["svd"]},
            {"name": "memory_map", "any_of": ["linker"]},
            {"name": "datasheet_or_reference", "any_of": ["datasheet", *sorted(REFERENCE_KIND_ALIASES)]},
        ],
        "optional_kinds": ["errata", "startup", "board"],
        "recommended_debug_backends": ["openocd-gdb", "pyocd-gdb", "jlink-gdb", "probe-rs-gdb"],
        "notes": [
            "Use exact package/capacity part numbers for linker memory maps.",
            "Keep reference manual and datasheet as separate manifest entries when both are available.",
        ],
    },
    {
        "id": "stm32f4",
        "vendor": "st",
        "family": "stm32f4",
        "match_prefixes": ["STM32F4"],
        "required_groups": [
            {"name": "register_map", "any_of": ["svd"]},
            {"name": "memory_map", "any_of": ["linker"]},
            {"name": "datasheet_or_reference", "any_of": ["datasheet", *sorted(REFERENCE_KIND_ALIASES)]},
        ],
        "optional_kinds": ["errata", "startup", "board"],
        "recommended_debug_backends": ["openocd-gdb", "pyocd-gdb", "jlink-gdb", "probe-rs-gdb"],
        "notes": ["Record exact flash/RAM density in the linker entry; STM32F4 parts vary widely by suffix."],
    },
    {
        "id": "nrf52",
        "vendor": "nordic",
        "family": "nrf52",
        "match_prefixes": ["NRF52", "NRF528"],
        "required_groups": [
            {"name": "register_map", "any_of": ["svd"]},
            {"name": "memory_map", "any_of": ["linker"]},
            {"name": "datasheet_or_reference", "any_of": ["datasheet", *sorted(REFERENCE_KIND_ALIASES)]},
        ],
        "optional_kinds": ["errata", "startup", "board"],
        "recommended_debug_backends": ["jlink-gdb", "probe-rs-gdb", "openocd-gdb"],
        "notes": ["Nordic product specification documents often contain both peripheral and electrical details."],
    },
    {
        "id": "rp2040",
        "vendor": "raspberrypi",
        "family": "rp2040",
        "match_prefixes": ["RP2040"],
        "required_groups": [
            {"name": "register_map", "any_of": ["svd"]},
            {"name": "memory_map", "any_of": ["linker"]},
            {"name": "datasheet_or_reference", "any_of": ["datasheet", *sorted(REFERENCE_KIND_ALIASES)]},
        ],
        "optional_kinds": ["startup", "board"],
        "recommended_debug_backends": ["openocd-gdb", "probe-rs-gdb"],
        "notes": ["Record board-level flash size separately from the RP2040 silicon identity."],
    },
    {
        "id": "gd32f1",
        "vendor": "gigadevice",
        "family": "gd32f1",
        "match_prefixes": ["GD32F1", "GD32F10"],
        "required_groups": [
            {"name": "register_map", "any_of": ["svd"]},
            {"name": "memory_map", "any_of": ["linker"]},
            {"name": "datasheet_or_reference", "any_of": ["datasheet", *sorted(REFERENCE_KIND_ALIASES)]},
        ],
        "optional_kinds": ["errata", "startup", "board"],
        "recommended_debug_backends": ["openocd-gdb", "jlink-gdb"],
        "notes": ["Do not assume STM32 register compatibility without a GD32-specific SVD or reference manual."],
    },
]


def profile_for_chip(chip: str | None) -> dict[str, Any]:
    normalized = _normalize_chip(chip)
    for profile in PROFILE_RULES:
        if any(normalized.startswith(prefix) for prefix in profile["match_prefixes"]):
            return _public_profile(profile, chip)
    return _public_profile(_generic_profile(), chip)


def manifest_template(chip: str | None) -> dict[str, Any]:
    profile = profile_for_chip(chip)
    part = chip or "<chip>"
    family = profile["family"]
    return {
        "schema_version": 1,
        "chip": part,
        "aliases": [],
        "vendor": profile["vendor"],
        "family": family,
        "documents": [
            {
                "kind": "datasheet",
                "local_path": f"documents/{part}_datasheet.md",
                "source_url": "<user-provided official datasheet URL>",
                "sha256": "<sha256 of source file when source_url is used>",
                "license_note": "<vendor license or redistribution note>",
            },
            {
                "kind": "reference_manual",
                "local_path": f"documents/{family}_reference_manual.md",
                "source_url": "<user-provided official reference manual URL>",
                "sha256": "<sha256 of source file when source_url is used>",
                "license_note": "<vendor license or redistribution note>",
            },
            {
                "kind": "errata",
                "local_path": f"documents/{part}_errata.md",
                "source_url": "<user-provided official errata URL if available>",
                "sha256": "<sha256 of source file when source_url is used>",
                "license_note": "<vendor license or redistribution note>",
            },
            {
                "kind": "svd",
                "local_path": f"svd/{part}.svd",
                "local_sha256": "<sha256 of local SVD file>",
            },
            {
                "kind": "linker",
                "local_path": f"linker/{part}.ld",
                "local_sha256": "<sha256 of local linker file>",
            },
            {
                "kind": "startup",
                "local_path": f"startup/startup_{family}.c",
                "local_sha256": "<sha256 of local startup/vector table file>",
            },
            {
                "kind": "board",
                "local_path": "board/board_notes.md",
                "local_sha256": "<sha256 of local board notes file>",
            },
        ],
    }


def lint_manifest(manifest_path: Path, chip: str | None = None, strict_hashes: bool = False) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "manifest_lint_failed",
            "manifest": str(manifest_path),
            "diagnostics": [
                _diag("manifest_json_invalid", "error", True, path=str(manifest_path), reason=str(exc)),
            ],
        }
    if not isinstance(manifest, dict):
        diagnostics.append(_diag("manifest_root_not_object", "error", True, path=str(manifest_path)))
        manifest = {}
    schema_version = manifest.get("schema_version", 1)
    if schema_version not in {1, "1"}:
        diagnostics.append(
            _diag(
                "unsupported_manifest_schema_version",
                "error",
                True,
                path=str(manifest_path),
                schema_version=schema_version,
            )
        )
    manifest_chip = manifest.get("chip")
    selected_chip = chip or str(manifest_chip) if manifest_chip else chip
    if not manifest_chip:
        diagnostics.append(_diag("manifest_chip_missing", "error", True, path=str(manifest_path)))
    elif chip and _normalize_chip(chip) != _normalize_chip(str(manifest_chip)):
        aliases = {_normalize_chip(str(alias)) for alias in manifest.get("aliases", [])}
        if _normalize_chip(chip) not in aliases:
            diagnostics.append(
                _diag(
                    "requested_chip_not_in_manifest",
                    "error",
                    True,
                    path=str(manifest_path),
                    requested_chip=chip,
                    manifest_chip=manifest_chip,
                )
            )
    profile = profile_for_chip(selected_chip)
    diagnostics.extend(_lint_vendor_family(manifest, manifest_path, profile))
    documents = manifest.get("documents")
    if not isinstance(documents, list):
        diagnostics.append(_diag("manifest_documents_not_list", "error", True, path=str(manifest_path)))
        documents = []
    document_kinds = _normalized_document_kinds(documents)
    diagnostics.extend(_lint_required_groups(document_kinds, profile, manifest_path))
    diagnostics.extend(_lint_document_entries(documents, manifest_path, strict_hashes))
    diagnostics.extend(_lint_layout(manifest_path, manifest, profile))
    blocks = [item for item in diagnostics if item.get("blocks")]
    return {
        "ok": not blocks,
        "status": "ok" if not blocks else "manifest_lint_failed",
        "manifest": str(manifest_path),
        "chip": selected_chip,
        "profile": profile,
        "diagnostics": diagnostics,
        "summary": {
            "document_count": len(documents),
            "document_kinds": sorted(document_kinds),
            "error_count": sum(1 for item in diagnostics if item.get("severity") == "error"),
            "warning_count": sum(1 for item in diagnostics if item.get("severity") == "warning"),
        },
    }


def _public_profile(profile: dict[str, Any], chip: str | None) -> dict[str, Any]:
    return {
        "id": profile["id"],
        "chip": chip,
        "vendor": profile["vendor"],
        "family": profile["family"],
        "required_groups": profile["required_groups"],
        "optional_kinds": profile["optional_kinds"],
        "recommended_debug_backends": profile["recommended_debug_backends"],
        "recommended_layout": f"vendors/{profile['vendor']}/{profile['family']}/{chip or '<chip>'}/manifest.json",
        "notes": profile["notes"],
    }


def _generic_profile() -> dict[str, Any]:
    return {
        "id": "generic-cortex-m",
        "vendor": "<vendor>",
        "family": "<family>",
        "match_prefixes": [],
        "required_groups": [
            {"name": "register_map", "any_of": ["svd"]},
            {"name": "memory_map", "any_of": ["linker"]},
            {"name": "datasheet_or_reference", "any_of": ["datasheet", *sorted(REFERENCE_KIND_ALIASES)]},
        ],
        "optional_kinds": ["errata", "startup", "board"],
        "recommended_debug_backends": ["openocd-gdb", "pyocd-gdb", "jlink-gdb", "probe-rs-gdb"],
        "notes": ["Unknown chip profile: ask the user for vendor/family-specific official documents and SVD."],
    }


def _lint_vendor_family(manifest: dict[str, Any], manifest_path: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for key in ("vendor", "family"):
        value = manifest.get(key)
        expected = profile.get(key)
        if not value:
            diagnostics.append(_diag(f"manifest_{key}_missing", "warning", False, path=str(manifest_path), expected=expected))
        elif expected and not str(expected).startswith("<") and str(value).lower() != str(expected).lower():
            diagnostics.append(
                _diag(
                    f"manifest_{key}_differs_from_profile",
                    "warning",
                    False,
                    path=str(manifest_path),
                    expected=expected,
                    actual=value,
                )
            )
    return diagnostics


def _lint_required_groups(document_kinds: set[str], profile: dict[str, Any], manifest_path: Path) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for group in profile["required_groups"]:
        accepted = {_normalize_kind(kind) for kind in group["any_of"]}
        if not document_kinds & accepted:
            diagnostics.append(
                _diag(
                    "required_document_group_missing",
                    "error",
                    True,
                    path=str(manifest_path),
                    group=group["name"],
                    accepted_kinds=sorted(accepted),
                )
            )
    optional = {_normalize_kind(kind) for kind in profile["optional_kinds"]}
    missing_optional = sorted(optional - document_kinds)
    if missing_optional:
        diagnostics.append(
            _diag(
                "optional_documents_missing",
                "warning",
                False,
                path=str(manifest_path),
                missing_kinds=missing_optional,
            )
        )
    return diagnostics


def _lint_document_entries(
    documents: list[Any],
    manifest_path: Path,
    strict_hashes: bool,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for index, item in enumerate(documents):
        if not isinstance(item, dict):
            diagnostics.append(_diag("manifest_document_not_object", "error", True, path=str(manifest_path), index=index))
            continue
        kind = item.get("kind")
        if not kind:
            diagnostics.append(_diag("manifest_document_missing_kind", "error", True, path=str(manifest_path), index=index))
        local_path = item.get("local_path")
        source_url = item.get("source_url")
        if not local_path and not source_url:
            diagnostics.append(
                _diag(
                    "manifest_document_missing_source",
                    "error",
                    True,
                    path=str(manifest_path),
                    index=index,
                    kind=kind,
                )
            )
            continue
        if source_url and not item.get("sha256"):
            diagnostics.append(
                _diag(
                    "source_url_without_sha256",
                    "warning" if not strict_hashes else "error",
                    strict_hashes,
                    path=str(manifest_path),
                    index=index,
                    kind=kind,
                )
            )
        if local_path:
            path = Path(str(local_path))
            if path.is_absolute():
                diagnostics.append(
                    _diag("manifest_local_path_absolute", "warning", False, path=str(manifest_path), index=index, local_path=str(local_path))
                )
            resolved = path if path.is_absolute() else manifest_path.parent / path
            if not resolved.exists():
                diagnostics.append(
                    _diag(
                        "manifest_local_path_missing",
                        "warning",
                        False,
                        path=str(manifest_path),
                        index=index,
                        kind=kind,
                        local_path=str(local_path),
                    )
                )
            if strict_hashes and not (item.get("local_sha256") or item.get("sha256")):
                diagnostics.append(
                    _diag(
                        "local_path_without_hash",
                        "error",
                        True,
                        path=str(manifest_path),
                        index=index,
                        kind=kind,
                        local_path=str(local_path),
                    )
                )
    return diagnostics


def _lint_layout(manifest_path: Path, manifest: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    vendor = str(manifest.get("vendor") or profile.get("vendor") or "").lower()
    family = str(manifest.get("family") or profile.get("family") or "").lower()
    chip = str(manifest.get("chip") or "").lower()
    lower_parts = [part.lower() for part in manifest_path.parts]
    expected = [part for part in ("vendors", vendor, family, chip) if part and not part.startswith("<")]
    if expected and not all(part in lower_parts for part in expected):
        return [
            _diag(
                "manifest_path_layout_unexpected",
                "warning",
                False,
                path=str(manifest_path),
                expected_layout=profile["recommended_layout"],
            )
        ]
    return []


def _normalized_document_kinds(documents: list[Any]) -> set[str]:
    kinds: set[str] = set()
    for item in documents:
        if isinstance(item, dict) and item.get("kind"):
            kinds.add(_normalize_kind(str(item["kind"])))
    return kinds


def _normalize_kind(kind: str) -> str:
    normalized = kind.strip().lower().replace("-", "_")
    if normalized in REFERENCE_KIND_ALIASES:
        return "reference_manual"
    return normalized


def _normalize_chip(chip: str | None) -> str:
    if not chip:
        return ""
    return "".join(ch for ch in str(chip).upper() if ch.isalnum())


def _diag(code: str, severity: str, blocks: bool, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "blocks": blocks, **extra}
