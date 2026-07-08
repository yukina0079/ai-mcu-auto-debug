from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .context_builder import build_mcu_context
from .profiles import REFERENCE_KIND_ALIASES, profile_for_chip
from .project_files import parse_linker_memory


DOCUMENT_EXTENSIONS = {".md", ".txt", ".pdf", ".html", ".htm"}
SVD_EXTENSIONS = {".svd"}
LINKER_EXTENSIONS = {".ld", ".lds"}
STARTUP_EXTENSIONS = {".c", ".s", ".S", ".asm"}
CHIP_SCAN_EXTENSIONS = {
    ".c",
    ".h",
    ".hpp",
    ".s",
    ".S",
    ".asm",
    ".inc",
    ".ld",
    ".lds",
    ".svd",
    ".xml",
    ".json",
    ".uvprojx",
}
IGNORED_DIRECTORY_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "debug_runs",
    "skills",
    ".embeddedskills",
    "knowledge_cache",
    "knowledge_repos",
}
DOC_SCAN_DIRECTORY_ALLOWLIST = {
    "docs",
    "doc",
    "documentation",
    "manuals",
    "references",
    "reference",
}
DOC_EXACT_FILENAMES = {
    "reference.md",
    "skill.md",
    "agents.md",
    "readme.md",
    "changelog.md",
}


def resolve_chip(
    project_path: Path,
    chip: str | None = None,
    svd_path: Path | None = None,
    startup_path: Path | None = None,
    linker_path: Path | None = None,
    target_path: Path | None = None,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    candidates: dict[str, dict[str, Any]] = {}

    if chip:
        _add_candidate(candidates, _normalize_chip(chip), 100, "explicit_chip", {"value": chip})
    for path, source in (
        (svd_path, "svd_path"),
        (startup_path, "startup_path"),
        (linker_path, "linker_path"),
        (target_path, "target_path"),
    ):
        if path:
            evidence.append({"source": source, "path": str(path)})
            _add_candidates_from_path(candidates, path, source, base_score=40)

    for path in _iter_project_files(project_path):
        _add_candidates_from_path(candidates, path, "project_file", base_score=20)

    ordered = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)
    explicit_chip = _normalize_chip(chip) if chip else None
    selected = explicit_chip or (ordered[0]["chip"] if ordered else None)
    ambiguous = False if explicit_chip else len(ordered) > 1 and ordered[0]["score"] == ordered[1]["score"]
    return {
        "ok": bool(selected) and not ambiguous,
        "selected": None if ambiguous else selected,
        "ambiguous": ambiguous,
        "candidates": ordered,
        "evidence": evidence,
        "reason": "ambiguous_chip" if ambiguous else "chip_resolved" if selected else "chip_not_found",
    }


def locate_docs(
    project_path: Path,
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    matched_manifests: list[dict[str, Any]] = []
    explicit = [
        ("svd", svd_path),
        ("linker", linker_path),
        ("startup", startup_path),
    ]
    explicit.extend(extra_docs or [])
    for kind, path in explicit:
        if path:
            entries.append(_manifest_entry(kind, path, trust_level="explicit"))

    roots = _candidate_roots(project_path, doc_repo_paths=doc_repo_paths)
    doc_repo_keys = {_path_key(path) for path in (doc_repo_paths or [])}
    for root in roots:
        is_doc_repo = _path_key(root) in doc_repo_keys
        if is_doc_repo and not root.exists():
            diagnostics.append(
                {
                    "code": "doc_repo_path_missing",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(root),
                    "reason": "configured_doc_repo_checkout_missing",
                    "next_action": "Run doc-repo-sync or provide a valid --doc-repo path.",
                }
            )
            continue
        trust_level = "doc_repo" if _path_key(root) in doc_repo_keys else _trust_for(root, project_path)
        files = _iter_files(root, mode="docs")
        manifest_files = [path for path in files if path.name == "manifest.json"]
        if is_doc_repo and root.exists() and not manifest_files:
            diagnostics.append(
                {
                    "code": "manifest_missing",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(root),
                    "reason": "doc_repo_contains_no_manifest_json",
                    "next_action": "Add vendors/<vendor>/<family>/<chip>/manifest.json to the MCU document repo.",
                }
            )
        matched_before = len(matched_manifests)
        for path in files:
            if path.name == "manifest.json":
                manifest_result = _manifest_entries_from_cache(
                    path,
                    chip,
                    default_trust_level=trust_level,
                    strict_repo=is_doc_repo,
                )
                entries.extend(manifest_result["entries"])
                diagnostics.extend(manifest_result["diagnostics"])
                if manifest_result.get("matched"):
                    matched_manifests.append(
                        {
                            "path": str(path),
                            "chip": manifest_result.get("chip"),
                            "aliases": manifest_result.get("aliases", []),
                        }
                    )
                continue
            kind = _classify_path(path, chip)
            if kind:
                entries.append(_manifest_entry(kind, path, trust_level=trust_level))
        if is_doc_repo and root.exists() and manifest_files and chip and len(matched_manifests) == matched_before:
            diagnostics.append(
                {
                    "code": "chip_manifest_not_found",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(root),
                    "chip": chip,
                    "manifest_count": len(manifest_files),
                    "reason": "doc_repo_has_manifests_but_none_match_requested_chip",
                    "next_action": "Add a manifest for the exact chip or fix aliases in the MCU document repo.",
                }
            )

    diagnostics.extend(_chip_alias_conflicts(matched_manifests, chip))
    deduped = _dedupe_entries(entries)
    missing = _missing_documents(deduped)
    blocking = _blocking_diagnostics(diagnostics)
    return {
        "ok": not any(item["required"] for item in missing) and not blocking,
        "chip": chip,
        "documents": deduped,
        "missing": missing,
        "diagnostics": diagnostics,
        "searched_roots": [str(root) for root in roots],
    }


def check_context(context_path: Path) -> dict[str, Any]:
    context = json.loads(context_path.read_text(encoding="utf-8"))
    missing: list[dict[str, Any]] = []
    if not context.get("chip"):
        missing.append({"kind": "chip", "required": True, "reason": "missing_chip_identity"})
    if not context.get("sources", {}).get("svd"):
        missing.append({"kind": "svd", "required": True, "reason": "missing_svd_source"})
    if not context.get("register_index"):
        missing.append({"kind": "register_index", "required": True, "reason": "missing_register_index"})
    elif any(not register.get("source") for register in context.get("register_index", {}).values()):
        missing.append({"kind": "register_sources", "required": True, "reason": "missing_register_source"})
    if not context.get("memory_regions"):
        missing.append({"kind": "memory_map", "required": True, "reason": "missing_memory_regions"})
    documents = context.get("sources", {}).get("documents", [])
    if any(not (doc.get("path") or doc.get("local_path")) for doc in documents):
        missing.append({"kind": "document_sources", "required": True, "reason": "missing_document_source_path"})
    kinds = {_canonical_doc_kind(str(doc.get("kind"))) for doc in documents if doc.get("kind")}
    if not ({"datasheet", "reference_manual"} & kinds):
        missing.append({"kind": "datasheet_or_reference", "required": True, "reason": "missing_datasheet_or_reference"})
    if "errata" not in kinds:
        missing.append({"kind": "errata", "required": False, "reason": "errata_missing"})
    dangerous_ranges = context.get("risk_rules", {}).get("dangerous_address_ranges")
    if not dangerous_ranges:
        missing.append({"kind": "dangerous_address_ranges", "required": True, "reason": "no_dangerous_address_rules"})
    return {
        "ok": not any(item["required"] for item in missing),
        "context": str(context_path),
        "chip": context.get("chip"),
        "missing": missing,
        "summary": {
            "memory_regions": len(context.get("memory_regions", [])),
            "register_index_entries": len(context.get("register_index", {})),
            "document_sources": len(context.get("sources", {}).get("documents", [])),
            "errata_risks": len(context.get("errata_risks", [])),
            "dangerous_address_ranges": len(dangerous_ranges or []),
        },
    }


def prepare_mcu(
    project_path: Path,
    output_path: Path,
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    board: str | None = None,
    package_name: str | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
) -> dict[str, Any]:
    resolved = resolve_chip(project_path, chip=chip, svd_path=svd_path, startup_path=startup_path, linker_path=linker_path)
    selected_chip = chip or resolved.get("selected")
    located = locate_docs(
        project_path,
        chip=selected_chip,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        extra_docs=extra_docs,
        doc_repo_paths=doc_repo_paths,
    )
    selected, selection_diagnostics = _select_inputs(
        located["documents"],
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        chip=selected_chip,
    )
    located.setdefault("diagnostics", []).extend(selection_diagnostics)
    required_missing = [
        item for item in located["missing"] if item["required"] and item["kind"] not in selected
    ]
    if not selected_chip:
        required_missing.append({"kind": "chip", "required": True, "reason": "missing_chip_identity"})
    blocking_diagnostics = _blocking_diagnostics(located.get("diagnostics", []))
    if blocking_diagnostics:
        return {
            "ok": False,
            "status": "doc_repo_diagnostics_failed",
            "resolve": resolved,
            "located": located,
            "missing": required_missing,
            "diagnostics": blocking_diagnostics,
            "next_actions": _next_actions_for_diagnostics(blocking_diagnostics),
        }
    if required_missing:
        return {
            "ok": False,
            "status": "missing_required_document",
            "resolve": resolved,
            "located": located,
            "missing": required_missing,
            "next_actions": _next_actions(required_missing),
        }

    context = build_mcu_context(
        chip=str(selected_chip),
        svd_path=selected["svd"],
        output_path=output_path,
        linker_path=selected.get("linker"),
        startup_path=selected.get("startup"),
        documents=[(entry["kind"], Path(entry["local_path"])) for entry in located["documents"] if entry["kind"] in {"datasheet", "reference", "reference_manual", "errata", "board"}],
        board=board,
        package_name=package_name,
    )
    check = check_context(output_path)
    return {
        "ok": check["ok"],
        "status": "ok" if check["ok"] else "context_incomplete",
        "output": str(output_path),
        "resolve": resolved,
        "manifest": located,
        "context_check": check,
        "artifacts": [{"kind": "mcu_context", "path": str(output_path), "registers": len(context["register_index"])}],
    }


def plan_document_intake(
    project_path: Path,
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
    output_path: Path = Path("examples/mcu_context.json"),
) -> dict[str, Any]:
    """Plan exactly which user-provided MCU documents are needed.

    This intentionally does not discover URLs or fetch documents. It gives the
    AI a deterministic checklist to ask the user for the smallest missing set.
    """

    resolved = resolve_chip(
        project_path,
        chip=chip,
        svd_path=svd_path,
        startup_path=startup_path,
        linker_path=linker_path,
    )
    selected_chip = chip or resolved.get("selected")
    located = locate_docs(
        project_path,
        chip=selected_chip,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        extra_docs=extra_docs,
        doc_repo_paths=doc_repo_paths,
    )
    requests = _document_requests(located.get("missing", []), selected_chip=selected_chip)
    if not selected_chip:
        requests.insert(0, _request_spec({"kind": "chip", "required": True, "reason": "missing_chip_identity"}, None))
    blocking = _blocking_diagnostics(located.get("diagnostics", []))
    required_requests = [item for item in requests if item["required"]]
    optional_requests = [item for item in requests if not item["required"]]
    status = (
        "doc_repo_diagnostics_failed"
        if blocking
        else "awaiting_user_documents"
        if required_requests
        else "ready_for_prepare_mcu"
    )
    return {
        "ok": not required_requests and not blocking,
        "status": status,
        "chip": selected_chip,
        "resolve": resolved,
        "found": _found_document_summary(located.get("documents", [])),
        "required_requests": required_requests,
        "optional_requests": optional_requests,
        "diagnostics": located.get("diagnostics", []),
        "blocking_diagnostics": blocking,
        "profile": profile_for_chip(selected_chip),
        "user_message_zh": _user_message_zh(required_requests, optional_requests),
        "commands": _intake_commands(selected_chip, output_path),
        "policy": {
            "web_search_allowed": False,
            "guess_vendor_url_allowed": False,
            "accepted_sources": ["user_file", "user_url", "project_file", "user_document_git_repo"],
        },
    }


def _iter_project_files(project_path: Path) -> list[Path]:
    return [
        path
        for path in _iter_files(project_path, mode="chip")
        if _is_likely_chip_identity_source(path, project_path)
    ]


def _iter_files(root: Path, mode: str = "all") -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        if _should_ignore_path(root, root.parent):
            return []
        return [root]
    files: list[Path] = []
    for path in root.rglob("*"):
        if _should_ignore_path(path, root):
            continue
        if mode == "docs" and path.is_file() and path.name != "manifest.json" and not _is_likely_project_document_path(path, root):
            continue
        if path.is_file():
            files.append(path)
    return files


def _should_ignore_path(path: Path, root: Path) -> bool:
    try:
        parts = {part.lower() for part in path.relative_to(root).parts}
    except ValueError:
        parts = {part.lower() for part in path.parts}
    return bool(parts & IGNORED_DIRECTORY_PARTS)


def _is_likely_project_document_path(path: Path, root: Path) -> bool:
    lower_name = path.name.lower()
    if lower_name in DOC_EXACT_FILENAMES:
        return False
    if path.suffix.lower() in SVD_EXTENSIONS | LINKER_EXTENSIONS:
        return True
    if path.suffix in STARTUP_EXTENSIONS and "startup" in lower_name:
        return True
    if path.suffix.lower() not in DOCUMENT_EXTENSIONS:
        return False
    try:
        relative_parts = {part.lower() for part in path.relative_to(root).parts[:-1]}
    except ValueError:
        relative_parts = {part.lower() for part in path.parts[:-1]}
    if relative_parts & DOC_SCAN_DIRECTORY_ALLOWLIST:
        return True
    return any(token in lower_name for token in ("datasheet", "errata", "manual", "rm0", "reference_manual", "pinout", "board"))


def _is_likely_chip_identity_source(path: Path, root: Path) -> bool:
    lower_name = path.name.lower()
    if "mcu_context" in lower_name or lower_name.endswith("_report.json"):
        return False
    if path.suffix.lower() in {".pdf", ".md", ".txt", ".html", ".htm"}:
        return False
    try:
        relative_parts = {part.lower() for part in path.relative_to(root).parts[:-1]}
    except ValueError:
        relative_parts = {part.lower() for part in path.parts[:-1]}
    if relative_parts & {"docs", "doc", "knowledge_cache"}:
        return False
    if path.suffix.lower() in {".json"}:
        return any(token in lower_name for token in ("target", "debug", "build", "config", "uvproj"))
    return path.suffix in CHIP_SCAN_EXTENSIONS


def _candidate_roots(project_path: Path, doc_repo_paths: list[Path] | None = None) -> list[Path]:
    cwd = Path.cwd()
    roots = [project_path, project_path / "docs", cwd / "docs", cwd / "examples" / "docs", cwd / "examples" / "svd", cwd / "knowledge_cache"]
    roots.extend(doc_repo_paths or [])
    return _dedupe_paths(roots)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _path_key(path: Path) -> str:
    return str(path.resolve()) if path.exists() else str(path)


def _classify_path(path: Path, chip: str | None = None) -> str | None:
    lower = path.name.lower()
    suffix = path.suffix.lower()
    if lower in DOC_EXACT_FILENAMES:
        return None
    if "debug_record" in lower or "mcu_debug_record" in lower:
        return None
    if suffix in SVD_EXTENSIONS:
        return "svd"
    if suffix in LINKER_EXTENSIONS and ("linker" in lower or "flash" in lower or "memory" in lower):
        return "linker"
    if suffix in STARTUP_EXTENSIONS and "startup" in lower:
        return "startup"
    if suffix not in DOCUMENT_EXTENSIONS:
        return None
    if "errata" in lower:
        return "errata"
    if "datasheet" in lower or "data_sheet" in lower:
        return "datasheet"
    if (
        "reference_manual" in lower
        or "technical_reference_manual" in lower
        or "programming_manual" in lower
        or "product_specification" in lower
        or "refman" in lower
        or re.search(r"\brm\d+", lower)
    ):
        return "reference_manual"
    if "board" in lower or "pinout" in lower:
        return "board"
    chip_family = _chip_family(chip)
    if chip_family and chip_family.lower() in lower:
        return "datasheet"
    return None


def _manifest_entry(kind: str, path: Path, trust_level: str) -> dict[str, Any]:
    local_sha256 = _sha256(path) if path.exists() and path.is_file() else None
    return {
        "kind": kind,
        "local_path": str(path),
        "sha256": local_sha256,
        "local_sha256": local_sha256,
        "trust_level": trust_level,
    }


def _manifest_entries_from_cache(
    manifest_path: Path,
    chip: str | None,
    default_trust_level: str = "cache",
    strict_repo: bool = False,
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "entries": [],
            "diagnostics": [
                {
                    "code": "unsupported_manifest",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(manifest_path),
                    "reason": "manifest_json_cannot_be_read_or_parsed",
                    "next_action": "Fix the manifest JSON or remove the invalid file.",
                }
            ],
            "matched": False,
        }
    if not isinstance(manifest, dict) or not isinstance(manifest.get("documents", []), list):
        return {
            "entries": [],
            "diagnostics": [
                {
                    "code": "unsupported_manifest",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(manifest_path),
                    "reason": "manifest_schema_missing_documents_list",
                    "next_action": "Use schema_version=1 and a documents[] list.",
                }
            ],
            "matched": False,
        }
    schema_version = manifest.get("schema_version", 1)
    if schema_version not in {1, "1"}:
        return {
            "entries": [],
            "diagnostics": [
                {
                    "code": "unsupported_manifest",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(manifest_path),
                    "schema_version": schema_version,
                    "reason": "unsupported_manifest_schema_version",
                    "next_action": "Convert this manifest to schema_version=1.",
                }
            ],
            "matched": False,
        }
    manifest_chip = manifest.get("chip")
    aliases = [str(alias) for alias in manifest.get("aliases", [])]
    normalized_aliases = {_normalize_chip(alias) for alias in aliases}
    if strict_repo and not manifest_chip:
        diagnostics.append(
            {
                "code": "unsupported_manifest",
                "severity": "warning",
                "blocks": False,
                "path": str(manifest_path),
                "reason": "doc_repo_manifest_missing_chip",
                "next_action": "Add an exact chip field to the document repo manifest.",
            }
        )
    matched = _manifest_matches_chip(chip, str(manifest_chip) if manifest_chip else None, normalized_aliases)
    if chip and not matched:
        return {
            "entries": [],
            "diagnostics": diagnostics,
            "matched": False,
            "chip": manifest_chip,
            "aliases": aliases,
        }
    entries: list[dict[str, Any]] = []
    for item in manifest.get("documents", []):
        local_path = item.get("local_path")
        kind = item.get("kind")
        if not kind:
            diagnostics.append(
                {
                    "code": "unsupported_manifest",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(manifest_path),
                    "reason": "manifest_document_missing_kind",
                    "entry": item,
                    "next_action": "Add kind to every manifest documents[] entry.",
                }
            )
            continue
        if not local_path:
            continue
        path = Path(local_path)
        if not path.exists():
            path = manifest_path.parent / local_path
        if not path.exists():
            diagnostics.append(
                {
                    "code": "local_path_missing",
                    "severity": "warning",
                    "blocks": False,
                    "path": str(manifest_path),
                    "kind": kind,
                    "local_path": str(local_path),
                    "reason": "manifest_local_path_does_not_exist",
                    "next_action": "Commit the referenced file or correct local_path in the manifest.",
                }
            )
            continue
        expected_local_hash = _expected_local_hash(item)
        actual_local_hash = _sha256(path) if path.is_file() else None
        if expected_local_hash and actual_local_hash and expected_local_hash.lower() != actual_local_hash.lower():
            diagnostics.append(
                {
                    "code": "hash_mismatch",
                    "severity": "error" if strict_repo else "warning",
                    "blocks": strict_repo,
                    "path": str(manifest_path),
                    "kind": kind,
                    "local_path": str(path),
                    "expected_sha256": expected_local_hash,
                    "actual_sha256": actual_local_hash,
                    "reason": "manifest_local_hash_does_not_match_file",
                    "next_action": "Verify the file, then update local_sha256 or revert the changed document.",
                }
            )
            continue
        entry = _manifest_entry(str(kind), path, trust_level=str(item.get("trust_level") or default_trust_level))
        for key in ("source_url", "source_domain", "downloaded_at", "content_type", "bytes", "license_note"):
            if key in item:
                entry[key] = item[key]
        if "sha256" in item:
            entry["manifest_sha256"] = item["sha256"]
            if item.get("source_url"):
                entry["source_sha256"] = item["sha256"]
        if "local_sha256" in item:
            entry["manifest_local_sha256"] = item["local_sha256"]
        entry["manifest_path"] = str(manifest_path)
        entries.append(entry)
    return {
        "entries": entries,
        "diagnostics": diagnostics,
        "matched": matched,
        "chip": manifest_chip,
        "aliases": aliases,
    }


def _manifest_matches_chip(chip: str | None, manifest_chip: str | None, normalized_aliases: set[str]) -> bool:
    if not chip:
        return True
    if not manifest_chip:
        return False
    normalized_chip = _normalize_chip(str(chip))
    return normalized_chip == _normalize_chip(str(manifest_chip)) or normalized_chip in normalized_aliases


def _expected_local_hash(item: dict[str, Any]) -> str | None:
    if item.get("local_sha256"):
        return str(item["local_sha256"])
    if item.get("sha256") and not item.get("source_url"):
        return str(item["sha256"])
    return None


def _chip_alias_conflicts(matched_manifests: list[dict[str, Any]], chip: str | None) -> list[dict[str, Any]]:
    if not chip:
        return []
    distinct_chips = {
        _normalize_chip(str(item.get("chip")))
        for item in matched_manifests
        if item.get("chip")
    }
    if len(distinct_chips) <= 1:
        return []
    return [
        {
            "code": "chip_alias_conflict",
            "severity": "error",
            "blocks": True,
            "requested_chip": chip,
            "matched_manifests": matched_manifests,
            "reason": "requested_chip_or_alias_matches_multiple_manifest_chips",
            "next_action": "Use an exact chip part number or fix aliases so they do not overlap across different chips.",
        }
    ]


def _blocking_diagnostics(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in diagnostics if item.get("blocks")]


def _trust_for(root: Path, project_path: Path) -> str:
    if root == project_path or project_path in root.parents:
        return "project"
    if "examples" in root.parts:
        return "example"
    if "knowledge_cache" in root.parts:
        return "cache"
    if "knowledge_repos" in root.parts or (root / ".git").exists():
        return "doc_repo"
    return "local"


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], int] = {}
    result: list[dict[str, Any]] = []
    for entry in entries:
        path = Path(entry["local_path"])
        resolved = str(path.resolve()) if path.exists() else entry["local_path"]
        key = (entry["kind"], entry.get("sha256") or resolved)
        if key in seen:
            existing_index = seen[key]
            if _entry_priority(entry) > _entry_priority(result[existing_index]):
                result[existing_index] = entry
            continue
        seen[key] = len(result)
        result.append(entry)
    return result


def _entry_priority(entry: dict[str, Any]) -> int:
    if entry.get("trust_level") == "explicit":
        return 100
    if entry.get("manifest_path"):
        return 80
    if entry.get("source_url"):
        return 70
    return 10


def _missing_documents(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kinds = {_canonical_doc_kind(str(entry["kind"])) for entry in entries}
    missing: list[dict[str, Any]] = []
    for kind in ("svd", "linker"):
        if kind not in kinds:
            missing.append({"kind": kind, "required": True, "reason": f"missing_{kind}"})
    if not ({"datasheet", "reference_manual"} & kinds):
        missing.append({"kind": "datasheet_or_reference", "required": True, "reason": "missing_datasheet_or_reference"})
    if "startup" not in kinds:
        missing.append({"kind": "startup", "required": False, "reason": "missing_startup"})
    if "errata" not in kinds:
        missing.append({"kind": "errata", "required": False, "reason": "errata_missing"})
    return missing


def _canonical_doc_kind(kind: str) -> str:
    normalized = kind.strip().lower().replace("-", "_")
    if normalized in REFERENCE_KIND_ALIASES:
        return "reference_manual"
    return normalized


def _select_inputs(
    entries: list[dict[str, Any]],
    svd_path: Path | None,
    linker_path: Path | None,
    startup_path: Path | None,
    chip: str | None = None,
) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    selected: dict[str, Path] = {}
    diagnostics: list[dict[str, Any]] = []
    for kind, explicit in (("svd", svd_path), ("linker", linker_path), ("startup", startup_path)):
        if explicit:
            selected[kind] = explicit
            continue
        match, ambiguous = _best_entry_for_kind(entries, kind, chip)
        if match:
            selected[kind] = Path(match["local_path"])
        if ambiguous:
            diagnostics.append(
                {
                    "code": "ambiguous_document_selection",
                    "severity": "warning",
                    "blocks": False,
                    "kind": kind,
                    "chip": chip,
                    "selected": str(match.get("local_path")),
                    "candidates": [str(entry.get("local_path")) for entry in ambiguous],
                    "reason": "multiple_document_candidates_have_same_selection_score",
                    "next_action": f"Pass --{kind} explicitly if the selected file is not the intended one.",
                }
            )
    return selected, diagnostics


def _best_entry_for_kind(entries: list[dict[str, Any]], kind: str, chip: str | None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    matches = [entry for entry in entries if entry["kind"] == kind]
    if not matches:
        return None, []
    scored = sorted(((entry, _selection_priority(entry, chip)) for entry in matches), key=lambda item: item[1], reverse=True)
    best_entry, best_score = scored[0]
    ambiguous = [entry for entry, score in scored if score == best_score]
    return best_entry, ambiguous if len(ambiguous) > 1 else []


def _selection_priority(entry: dict[str, Any], chip: str | None) -> tuple[int, int, str]:
    path_text = str(entry.get("local_path", "")).lower().replace("\\", "/")
    normalized_path = _normalize_chip(path_text)
    normalized_chip = _normalize_chip(chip or "")
    score = _entry_priority(entry)
    if normalized_chip and normalized_chip in normalized_path:
        score += 100
    family = _chip_family(chip)
    if family and _normalize_chip(family) in normalized_path:
        score += 20
    if entry.get("manifest_path"):
        score += 30
    trust = entry.get("trust_level")
    if trust == "project":
        score += 25
    if trust in {"doc_repo", "vendor_manifest", "project_example", "project_subset"}:
        score += 20
    return score, len(path_text), path_text


def _chip_candidates_from_text(text: str) -> list[str]:
    candidates = re.findall(r"stm32[a-z]?\d{3}[a-z0-9]{0,6}", text, flags=re.IGNORECASE)
    return [_normalize_chip(candidate) for candidate in candidates]


def _add_candidates_from_path(
    candidates: dict[str, dict[str, Any]],
    path: Path,
    source: str,
    base_score: int,
) -> None:
    for candidate in _chip_candidates_from_text(path.name):
        _add_candidate(candidates, candidate, base_score, f"{source}_name", {"path": str(path)})
    for candidate in _chip_candidates_from_file(path):
        _add_candidate(candidates, candidate, max(10, base_score - 10), f"{source}_content", {"path": str(path)})
    for hint in _linker_capacity_hints(path, candidates):
        _add_candidate(
            candidates,
            hint["chip"],
            45,
            "linker_memory_map",
            {"path": str(path), "flash_bytes": hint["flash_bytes"], "capacity_code": hint["capacity_code"]},
        )


def _chip_candidates_from_file(path: Path, max_bytes: int = 256 * 1024) -> list[str]:
    if path.suffix not in CHIP_SCAN_EXTENSIONS or not path.exists() or not path.is_file():
        return []
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return []
    text = data.decode("utf-8", errors="ignore")
    return _chip_candidates_from_text(text)


def _linker_capacity_hints(path: Path, candidates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if path.suffix.lower() not in LINKER_EXTENSIONS or not path.exists():
        return []
    try:
        regions = parse_linker_memory(path)
    except Exception:
        return []
    flash = next((region for region in regions if str(region.get("name", "")).upper() == "FLASH"), None)
    if not flash:
        return []
    code = _stm32_capacity_code(int(flash["length"]))
    if not code:
        return []
    family = _best_stm32_family(candidates) or _chip_family_from_path(path)
    if not family:
        return []
    return [{"chip": f"{family}X{code}", "flash_bytes": int(flash["length"]), "capacity_code": code}]


def _best_stm32_family(candidates: dict[str, dict[str, Any]]) -> str | None:
    ordered = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)
    for candidate in ordered:
        family = _chip_family(candidate["chip"])
        if family and family.startswith("STM32"):
            return family
    return None


def _chip_family_from_path(path: Path) -> str | None:
    candidates = _chip_candidates_from_text(path.name) + _chip_candidates_from_file(path)
    for candidate in candidates:
        family = _chip_family(candidate)
        if family and family.startswith("STM32"):
            return family
    return None


def _stm32_capacity_code(flash_bytes: int) -> str | None:
    return {
        16 * 1024: "4",
        32 * 1024: "6",
        64 * 1024: "8",
        128 * 1024: "B",
        256 * 1024: "C",
        384 * 1024: "D",
        512 * 1024: "E",
        768 * 1024: "G",
        1024 * 1024: "I",
    }.get(flash_bytes)


def _normalize_chip(value: str) -> str:
    return value.replace("_", "").replace("-", "").upper()


def _chip_family(chip: str | None) -> str | None:
    if not chip:
        return None
    match = re.match(r"(STM32[A-Z]?\d{3})", chip.upper())
    return match.group(1) if match else chip.upper()


def _add_candidate(candidates: dict[str, dict[str, Any]], chip: str, score: int, source: str, evidence: dict[str, Any]) -> None:
    item = candidates.setdefault(chip, {"chip": chip, "score": 0, "evidence": []})
    item["score"] += score
    item["evidence"].append({"source": source, **evidence})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _next_actions(missing: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in missing:
        kind = item["kind"]
        if kind == "svd":
            actions.append("Ask the user to provide a CMSIS-SVD file or a trusted CMSIS-Pack URL/file.")
        elif kind == "linker":
            actions.append("Ask the user to provide a linker script or memory map so Flash/RAM ranges can be validated.")
        elif kind == "datasheet_or_reference":
            actions.append("Ask the user to provide a datasheet or reference manual excerpt/file for evidence-backed conclusions.")
        elif kind == "chip":
            actions.append("Ask the user to provide the exact MCU part number, package, and revision if known.")
    return actions


def _document_requests(missing: list[dict[str, Any]], selected_chip: str | None) -> list[dict[str, Any]]:
    requests = [_request_spec(item, selected_chip) for item in missing]
    kinds = {request["kind"] for request in requests}
    if "board_notes" not in kinds:
        requests.append(_request_spec({"kind": "board_notes", "required": False, "reason": "board_notes_optional"}, selected_chip))
    return requests


def _request_spec(item: dict[str, Any], selected_chip: str | None) -> dict[str, Any]:
    kind = item["kind"]
    specs = {
        "chip": {
            "label": "精确 MCU 型号",
            "why_needed": "用于选择正确 datasheet、SVD、Flash/RAM 容量和调试目标。",
            "accepted_inputs": ["完整芯片丝印", "芯片型号字符串", "封装/修订号备注"],
            "cli_flags": ["--chip <part-number>"],
            "example": "--chip STM32F103RCT6",
        },
        "svd": {
            "label": "CMSIS-SVD 或 CMSIS-Pack",
            "why_needed": "用于生成寄存器地址、字段、access type 和 reserved bits，避免寄存器解释幻觉。",
            "accepted_inputs": [".svd 文件", ".pack 文件", "用户提供的可信 CMSIS-Pack URL"],
            "cli_flags": ["--svd <device.svd>", "--url cmsis_pack=<pack-file-or-url>"],
            "example": "--svd STM32F103.svd",
        },
        "linker": {
            "label": "linker script 或内存映射",
            "why_needed": "用于确认 Flash/RAM 起止地址，保护内存读写和调试报告范围判断。",
            "accepted_inputs": [".ld/.lds linker script", "包含 Flash/RAM 起止地址的 memory map 文本"],
            "cli_flags": ["--linker <linker.ld>"],
            "example": "--linker linker.ld",
        },
        "datasheet_or_reference": {
            "label": "datasheet 或 reference manual",
            "why_needed": "用于引用官方功能描述、外设说明、调试限制和安全结论证据。",
            "accepted_inputs": ["PDF", "HTML", "Markdown/TXT 摘要", "用户提供的官方 URL"],
            "cli_flags": ["--doc datasheet=<file>", "--doc reference_manual=<file>", "--url datasheet=<file-or-url>"],
            "example": "--doc reference_manual=RM0008.pdf",
        },
        "startup": {
            "label": "startup/vector table 文件",
            "why_needed": "可选；用于确认中断向量表和 Reset_Handler，提升启动/断点判断质量。",
            "accepted_inputs": ["startup_*.c", "startup_*.s", "vector table 源文件"],
            "cli_flags": ["--startup <startup.c>"],
            "example": "--startup startup_stm32f103.c",
        },
        "errata": {
            "label": "errata 文档",
            "why_needed": "可选但建议提供；缺失时会记录 errata_missing，不能声称没有芯片风险。",
            "accepted_inputs": ["errata PDF", "Markdown/TXT 摘要", "用户提供的官方 URL"],
            "cli_flags": ["--doc errata=<file>", "--url errata=<file-or-url>"],
            "example": "--doc errata=ES0340.pdf",
        },
        "board_notes": {
            "label": "板卡说明/原理图/接线备注",
            "why_needed": "可选但建议提供；用于解释 LED、按键、BOOT、NRST、SWD、串口等板级连接。",
            "accepted_inputs": ["README/Markdown", "原理图 PDF", "引脚接线表", "文字说明"],
            "cli_flags": ["--doc board=<file>"],
            "example": "--doc board=board_notes.md",
        },
    }
    spec = specs.get(
        kind,
        {
            "label": kind,
            "why_needed": item.get("reason", "missing_document"),
            "accepted_inputs": ["用户提供的文件或 URL"],
            "cli_flags": [f"--doc {kind}=<file>"],
            "example": f"--doc {kind}=<file>",
        },
    )
    return {
        "kind": kind,
        "required": bool(item.get("required")),
        "reason": item.get("reason"),
        "chip": selected_chip,
        **spec,
        "question_zh": f"请提供{spec['label']}（可接受：{'、'.join(spec['accepted_inputs'])}）。",
    }


def _found_document_summary(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        item = {
            "path": entry.get("local_path"),
            "trust_level": entry.get("trust_level"),
            "sha256": entry.get("sha256"),
        }
        if entry.get("source_url"):
            item["source_url"] = entry.get("source_url")
        found.setdefault(str(entry.get("kind")), []).append({key: value for key, value in item.items() if value})
    return found


def _user_message_zh(required: list[dict[str, Any]], optional: list[dict[str, Any]]) -> str:
    if not required:
        if optional:
            labels = "、".join(item["label"] for item in optional)
            return f"必需资料已齐，可以生成 MCU 知识库。可选增强资料：{labels}。"
        return "必需资料已齐，可以生成 MCU 知识库。"
    lines = ["为了生成可追溯的 MCU 知识库，请提供以下资料："]
    for index, item in enumerate(required, start=1):
        lines.append(f"{index}. {item['label']}：{item['why_needed']} 可接受：{'、'.join(item['accepted_inputs'])}。")
    if optional:
        labels = "、".join(item["label"] for item in optional)
        lines.append(f"可选增强资料：{labels}。")
    return "\n".join(lines)


def _intake_commands(selected_chip: str | None, output_path: Path) -> dict[str, str]:
    chip = selected_chip or "<chip>"
    manifest = f"knowledge_cache/user/{chip}/manifest.json"
    return {
        "direct_prepare_template": (
            "python -m ai_mcu_debug.cli prepare-mcu --project . "
            f"--chip {chip} --svd <device.svd> --linker <linker.ld> --startup <startup.c> "
            "--doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> "
            f"--doc errata=<errata.pdf-or-md> --output {output_path}"
        ),
        "cache_user_files_template": (
            f"python -m ai_mcu_debug.cli fetch-docs --chip {chip} --manifest {manifest} "
            "--url datasheet=<user-provided-datasheet> --url reference_manual=<user-provided-reference> "
            "--url errata=<user-provided-errata> --url cmsis_pack=<user-provided-pack>"
        ),
        "ingest_cached_template": (
            f"python -m ai_mcu_debug.cli ingest-docs --manifest {manifest} --chip {chip} "
            f"--svd <device.svd> --linker <linker.ld> --startup <startup.c> --output {output_path}"
        ),
    }


def _next_actions_for_diagnostics(diagnostics: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in diagnostics:
        action = item.get("next_action")
        if action and str(action) not in actions:
            actions.append(str(action))
    return actions
