from __future__ import annotations

import json
import sys
from pathlib import Path

import ai_mcu_debug.api as api
from ai_mcu_debug.api import (
    accept_nonvision,
    build_firmware,
    check_prepared_context,
    collect_runtime_log,
    check_environment,
    diagnose_connection,
    export_debug_handoff,
    fetch_user_documents,
    get_workspace_status,
    initialize_workspace,
    ingest_user_documents,
    install_skill_package,
    locate_mcu_documents,
    plan_docs,
    plan_next_workflow,
    prepare_context,
    read_hardware_id,
    repair_build,
    resolve_mcu_chip,
    run_next_workflow,
    run_ai_debug,
    run_debug_op,
    scan_debug_probes_api,
    smoke_test_firmware,
    sync_document_repo,
    validate_target_config,
    write_debug_record,
)
from ai_mcu_debug.models import DebugTargetConfig
from tests.test_hardware_identity import IdentityDebugAdapter


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_prepare_context_api_returns_json_report(tmp_path: Path) -> None:
    output = tmp_path / "mcu_context.json"

    report = prepare_context(
        project=PROJECT,
        output=output,
        chip="STM32F103RCT6",
        svd=SVD,
        linker=LINKER,
        startup=STARTUP,
        docs=[f"datasheet={DATASHEET}", f"errata={ERRATA}"],
    )

    assert report["ok"] is True
    assert report["output"] == str(output)
    assert output.exists()


def test_plan_docs_api_returns_user_request_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = plan_docs(project=project, chip="STM32F103RCT6")

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert any(item["kind"] == "svd" for item in report["required_requests"])
    assert report["policy"]["web_search_allowed"] is False


def test_plan_next_workflow_api_returns_tool_recommendations(tmp_path: Path) -> None:
    project = tmp_path / "empty_project"
    project.mkdir()

    report = plan_next_workflow(project=project, context=tmp_path / "mcu_context.json", chip="STM32F103RCT6")

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert report["user_requests"]
    assert report["policy"]["side_effects"] is False


def test_run_next_workflow_api_stops_for_user_documents(tmp_path: Path) -> None:
    project = tmp_path / "empty_project"
    project.mkdir()

    report = run_next_workflow(
        project=project,
        context=tmp_path / "mcu_context.json",
        workspace_config=tmp_path / ".embeddedskills/config.json",
        report_dir=tmp_path / "workflow_run",
        chip="STM32F103RCT6",
    )

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert report["user_requests"]
    assert report["policy"]["flash_allowed"] is False


def test_document_intake_api_tools_cover_user_to_context_flow(tmp_path: Path) -> None:
    resolved = resolve_mcu_chip(project=PROJECT, chip="STM32F103RCT6", svd=SVD, linker=LINKER, startup=STARTUP)
    assert resolved["ok"] is True
    assert resolved["selected"] == "STM32F103RCT6"

    located = locate_mcu_documents(
        project=PROJECT,
        chip="STM32F103RCT6",
        svd=SVD,
        linker=LINKER,
        startup=STARTUP,
        docs=[f"datasheet={DATASHEET}", f"errata={ERRATA}"],
    )
    assert located["ok"] is True
    assert {item["kind"] for item in located["documents"]} >= {"svd", "linker", "startup", "datasheet", "errata"}

    manifest = tmp_path / "manifest.json"
    fetched = fetch_user_documents(
        chip="STM32F103RCT6",
        manifest=manifest,
        urls=[f"datasheet={DATASHEET}", f"errata={ERRATA}"],
    )
    assert fetched["ok"] is True
    assert manifest.exists()
    assert {item["source_domain"] for item in fetched["documents"]} == {"local_file"}

    context = tmp_path / "mcu_context.json"
    ingested = ingest_user_documents(
        manifest=manifest,
        output=context,
        chip="STM32F103RCT6",
        svd=SVD,
        linker=LINKER,
        startup=STARTUP,
    )
    assert ingested["ok"] is True
    assert context.exists()

    checked = check_prepared_context(context=context)
    assert checked["ok"] is True

    record = tmp_path / "MCU_DEBUG_RECORD.md"
    written = write_debug_record(context=context, output=record)
    assert written["ok"] is True
    assert record.exists()


def test_sync_document_repo_api_requires_user_repo_url(tmp_path: Path) -> None:
    report = sync_document_repo(local_path=tmp_path / "missing-doc-repo")

    assert report["ok"] is False
    assert report["status"] == "missing_repo_url"


def test_environment_api_tools_are_safe_small_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        api,
        "run_doctor",
        lambda debug_backend=None, build_backend=None: {
            "ok": True,
            "debug_backend": debug_backend,
            "build_backend": build_backend,
        },
    )
    monkeypatch.setattr(
        api,
        "scan_debug_probes",
        lambda: {"ok": True, "probes": [{"matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"]}]},
    )

    doctor = check_environment(debug_backend="openocd-gdb", build_backend="cmake")
    probes = scan_debug_probes_api()

    assert doctor["ok"] is True
    assert doctor["debug_backend"] == "openocd-gdb"
    assert probes["ok"] is True


def test_initialize_workspace_api_can_skip_host_checks(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text("{}", encoding="utf-8")
    build_config = tmp_path / "build.json"
    build_config.write_text("{}", encoding="utf-8")

    report = initialize_workspace(
        output_dir=tmp_path / ".embeddedskills",
        project=project,
        context=context,
        build_config=build_config,
        generate_templates=False,
        run_doctor_check=False,
        scan_probes=False,
    )

    assert report["ok"] is True
    assert Path(report["config"]).exists()
    assert report["workspace"]["build"]["config"] == str(build_config)


def test_validate_target_config_api_without_probe_scan(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(
            {
                "backend": "openocd-gdb",
                "server_command": [
                    "openocd",
                    "-f",
                    "interface/cmsis-dap.cfg",
                    "-c",
                    "transport select swd",
                    "-f",
                    "target/stm32f1x.cfg",
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_target_config(target=target)

    assert report["ok"] is True
    assert report["interface"] == "cmsis-dap"
    assert report["transport"] == "swd"


def test_connection_diagnose_api_reports_missing_target(tmp_path: Path) -> None:
    report = diagnose_connection(workspace_config=tmp_path / "missing_config.json")

    assert report["ok"] is False
    assert report["status"] == "target_config_missing"


def test_build_runtime_api_tools_use_configured_commands(tmp_path: Path) -> None:
    config = tmp_path / "build.json"
    config.write_text(
        json.dumps(
            {
                "backend": "command",
                "source_dir": str(tmp_path),
                "build_command": [sys.executable, "-c", "print('build ok')"],
                "smoke_test_command": [sys.executable, "-c", "print('smoke ok')"],
                "runtime_log_command": [sys.executable, "-c", "print('uart ready')"],
            }
        ),
        encoding="utf-8",
    )

    build = build_firmware(config=config)
    smoke = smoke_test_firmware(config=config)
    runtime = collect_runtime_log(config=config)
    repair = repair_build(config=config)

    assert build["ok"] is True
    assert "build ok" in build["result"]["stdout"]
    assert smoke["ok"] is True
    assert "smoke ok" in smoke["result"]["stdout"]
    assert runtime["ok"] is True
    assert runtime["result"]["observations"] == ["uart ready"]
    assert repair["ok"] is False
    assert repair["status"] == "repair_blocked_by_policy"


def test_accept_nonvision_api_stops_for_missing_user_documents(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = accept_nonvision(
        project=project,
        context=tmp_path / "mcu_context.json",
        report_dir=tmp_path / "acceptance",
        handoff_project=tmp_path,
        chip="STM32F103RCT6",
        scan_probes=False,
    )

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert report["policy"]["ai_debug_mode"] == "dry-run"
    assert report["policy"]["flash_allowed"] is False


def test_prepare_context_api_accepts_doc_repo(tmp_path: Path) -> None:
    output = tmp_path / "mcu_context.json"
    repo_chip_dir = tmp_path / "mcu-docs" / "vendors" / "st" / "stm32f1" / "STM32F103RCT6"
    docs_dir = repo_chip_dir / "documents"
    docs_dir.mkdir(parents=True)
    datasheet = docs_dir / "datasheet.md"
    datasheet.write_text("STM32F103RCT6 datasheet notes. Flash starts at 0x08000000.", encoding="utf-8")
    errata = docs_dir / "errata.md"
    errata.write_text("No local errata note beyond vendor URL.", encoding="utf-8")
    svd = repo_chip_dir / "svd" / "device.svd"
    svd.parent.mkdir()
    svd.write_text(SVD.read_text(encoding="utf-8"), encoding="utf-8")
    linker = repo_chip_dir / "linker" / "linker.stm32f103rct6.ld"
    linker.parent.mkdir()
    linker.write_text(LINKER.read_text(encoding="utf-8"), encoding="utf-8")
    (repo_chip_dir / "manifest.json").write_text(
        (
            '{"chip":"STM32F103RCT6","documents":['
            '{"kind":"datasheet","local_path":"documents/datasheet.md"},'
            '{"kind":"errata","local_path":"documents/errata.md"},'
            '{"kind":"svd","local_path":"svd/device.svd"},'
            '{"kind":"linker","local_path":"linker/linker.stm32f103rct6.ld"}'
            ']}'
        ),
        encoding="utf-8",
    )

    report = prepare_context(
        project=PROJECT,
        output=output,
        chip="STM32F103RCT6",
        doc_repos=[tmp_path / "mcu-docs"],
    )

    assert report["ok"] is True
    assert output.exists()


def test_run_ai_debug_api_defaults_to_safe_policy(tmp_path: Path) -> None:
    report = run_ai_debug(
        mode="not-a-mode",
        project=PROJECT,
        context=tmp_path / "missing_context.json",
        report_dir=tmp_path / "report",
        workspace_config=tmp_path / "missing_config.json",
    )

    assert report["ok"] is False
    assert report["status"] == "unsupported_mode"
    assert report["safety"]["flash_allowed"] is False
    assert report["safety"]["repair_allowed"] is False
    assert report["safety"]["force_allowed"] is False


def test_run_debug_op_api_blocks_write_without_context_before_connecting(tmp_path: Path) -> None:
    report = run_debug_op(
        target=tmp_path / "target_does_not_need_to_exist.json",
        operation="write-register",
        register="GPIOC.CRH",
        value="0x00200000",
    )

    assert report["ok"] is False
    assert report["guard"]["reason"] == "mcu_context_required_for_write_operation"


def test_run_debug_op_api_blocks_unknown_memory_write_with_context_before_connecting(tmp_path: Path) -> None:
    context = prepare_context(
        project=PROJECT,
        output=tmp_path / "mcu_context.json",
        chip="STM32F103RCT6",
        svd=SVD,
        linker=LINKER,
        startup=STARTUP,
        docs=[f"datasheet={DATASHEET}", f"errata={ERRATA}"],
    )

    report = run_debug_op(
        target=tmp_path / "target_does_not_need_to_exist.json",
        operation="write-memory",
        context=context["output"],
        address="0x50000000",
        data_hex="01020304",
    )

    assert report["ok"] is False
    assert report["guard"]["checks"][0]["reason"] == "unknown_or_unapproved_address"


def test_read_hardware_id_api_uses_configured_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api, "load_target_config", lambda path: DebugTargetConfig(backend="fake"))
    monkeypatch.setattr(api, "create_debug_adapter", lambda config: IdentityDebugAdapter())

    report = read_hardware_id(target=tmp_path / "target.json", chip="STM32F103RCT6", report_dir=tmp_path)

    assert report["ok"] is True
    assert report["decoded"]["cortex_m_cpuid"]["part_name"] == "Cortex-M3"
    assert report["expected_chip_check"]["compatible"] is True


def test_export_debug_handoff_api_returns_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "mcu_context.json").write_text("{}", encoding="utf-8")

    report = export_debug_handoff(output=tmp_path / "handoff", project=project)

    assert report["ok"] is True
    assert Path(report["manifest"]).exists()


def test_install_skill_package_api_installs_to_explicit_destination(tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text("skill", encoding="utf-8")
    (source / "REFERENCE.md").write_text("reference", encoding="utf-8")
    destination = tmp_path / "codex" / "skills" / "mcu-auto-debug"

    report = install_skill_package(source=source, destination=destination)

    assert report["ok"] is True
    assert report["status"] == "installed"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "skill"


def test_get_workspace_status_api_reports_missing_config(tmp_path: Path) -> None:
    report = get_workspace_status(config=tmp_path / "missing.json")

    assert report["ok"] is False
    assert report["reason"] == "workspace_config_missing"
