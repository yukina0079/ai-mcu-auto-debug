from __future__ import annotations

import inspect
import json

import ai_mcu_debug.api as api
from ai_mcu_debug.mcp_server import McpServer


def test_mcp_server_lists_core_tools() -> None:
    response = McpServer().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert {
        "prepare_mcu_context",
        "plan_document_intake",
        "workflow_plan",
        "workflow_run",
        "capability_audit",
        "mcp_config",
        "mcp_smoke",
        "skill_bootstrap",
        "resolve_chip",
        "locate_documents",
        "fetch_user_documents",
        "ingest_documents",
        "sync_document_repo",
        "check_mcu_context",
        "write_debug_record",
        "doctor",
        "probe_scan",
        "init_workspace",
        "validate_target",
        "connection_diagnose",
        "setup_project",
        "build_firmware",
        "smoke_test_firmware",
        "collect_runtime_log",
        "repair_build",
        "install_skill",
        "mcu_profile",
        "lint_mcu_manifest",
        "accept_nonvision",
        "run_ai_debug",
        "debug_op_guarded",
        "read_hardware_id",
        "export_handoff",
        "replay_handoff",
        "workspace_status",
    } <= tool_names


def test_mcp_server_lists_explicit_tool_input_schemas() -> None:
    response = McpServer().handle({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})

    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name, tool in tools.items():
        schema = tool["inputSchema"]
        assert schema["type"] == "object", name
        assert "properties" in schema, name
        assert schema.get("additionalProperties") is False, name


def test_mcp_server_schema_guides_policy_sensitive_tools() -> None:
    response = McpServer().handle({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})

    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    ai_debug_schema = tools["run_ai_debug"]["inputSchema"]
    assert ai_debug_schema["properties"]["mode"]["enum"] == ["dry-run", "read-only", "run"]
    assert ai_debug_schema["properties"]["allow_flash"]["default"] is False
    assert ai_debug_schema["properties"]["allow_repair"]["default"] is False

    repair_schema = tools["repair_build"]["inputSchema"]
    assert repair_schema["required"] == ["config"]
    assert repair_schema["properties"]["allow_repair"]["default"] is False

    debug_schema = tools["debug_op_guarded"]["inputSchema"]
    assert debug_schema["required"] == ["target", "operation"]
    assert "write-memory" in debug_schema["properties"]["operation"]["enum"]


def test_mcp_server_schemas_match_public_api_parameters() -> None:
    response = McpServer().handle({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})

    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    api_functions = {
        "prepare_mcu_context": api.prepare_context,
        "plan_document_intake": api.plan_docs,
        "workflow_plan": api.plan_next_workflow,
        "workflow_run": api.run_next_workflow,
        "capability_audit": api.audit_project_capabilities,
        "mcp_config": api.generate_mcp_client_config,
        "mcp_smoke": api.smoke_test_mcp_server,
        "skill_bootstrap": api.bootstrap_skill,
        "resolve_chip": api.resolve_mcu_chip,
        "locate_documents": api.locate_mcu_documents,
        "fetch_user_documents": api.fetch_user_documents,
        "ingest_documents": api.ingest_user_documents,
        "sync_document_repo": api.sync_document_repo,
        "check_mcu_context": api.check_prepared_context,
        "write_debug_record": api.write_debug_record,
        "doctor": api.check_environment,
        "probe_scan": api.scan_debug_probes_api,
        "init_workspace": api.initialize_workspace,
        "validate_target": api.validate_target_config,
        "connection_diagnose": api.diagnose_connection,
        "setup_project": api.setup_project,
        "build_firmware": api.build_firmware,
        "smoke_test_firmware": api.smoke_test_firmware,
        "collect_runtime_log": api.collect_runtime_log,
        "repair_build": api.repair_build,
        "install_skill": api.install_skill_package,
        "mcu_profile": api.get_mcu_profile,
        "lint_mcu_manifest": api.lint_mcu_manifest,
        "accept_nonvision": api.accept_nonvision,
        "run_ai_debug": api.run_ai_debug,
        "read_hardware_id": api.read_hardware_id,
        "export_handoff": api.export_debug_handoff,
        "replay_handoff": api.replay_debug_handoff,
        "workspace_status": api.get_workspace_status,
    }
    for tool_name, function in api_functions.items():
        schema_properties = set(tools[tool_name]["inputSchema"]["properties"])
        public_parameters = set(inspect.signature(function).parameters)
        assert schema_properties <= public_parameters, tool_name


def test_mcp_server_rejects_invalid_tool_arguments_before_handler() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "repair_build", "arguments": {"allow_repair": True}},
        }
    )

    assert response["result"]["isError"] is True
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "invalid_arguments"
    assert payload["errors"][0]["code"] == "missing_required"
    assert "traceback" not in payload


def test_mcp_server_rejects_unknown_and_bad_enum_arguments() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "run_ai_debug", "arguments": {"mode": "flash-now", "surprise": True}},
        }
    )

    assert response["result"]["isError"] is True
    payload = json.loads(response["result"]["content"][0]["text"])
    assert {error["code"] for error in payload["errors"]} == {"invalid_enum", "unexpected_property"}


def test_mcp_server_calls_workspace_status_tool() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "workspace_status", "arguments": {"config": "definitely_missing_config.json"}},
        }
    )

    assert response["result"]["content"][0]["type"] == "text"
    assert "workspace_config_missing" in response["result"]["content"][0]["text"]


def test_mcp_server_calls_resolve_chip_tool() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "resolve_chip", "arguments": {"project": ".", "chip": "STM32F103RCT6"}},
        }
    )

    assert response["result"]["isError"] is False
    assert "STM32F103RCT6" in response["result"]["content"][0]["text"]


def test_mcp_server_calls_capability_audit_tool() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "capability_audit", "arguments": {"project": "."}},
        }
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "nonvision_ready"


def test_mcp_server_calls_mcp_config_tool() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "mcp_config", "arguments": {"project": ".", "client": "generic-json"}},
        }
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["config"]["mcpServers"]["ai_mcu_debug"]["args"] == ["-m", "ai_mcu_debug.cli", "mcp-server"]


def test_mcp_server_calls_mcp_smoke_tool() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "mcp_smoke", "arguments": {"project": ".", "required_tools": ["mcp_config"]}},
        }
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "ok"


def test_mcp_server_calls_skill_bootstrap_tool() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "skill_bootstrap",
                "arguments": {"project": ".", "dry_run": True, "skip_install": True},
            },
        }
    )

    assert response["result"]["isError"] is False
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["status"] == "would_bootstrap"


def test_mcp_server_unknown_tool_returns_tool_error() -> None:
    response = McpServer().handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
    )

    assert response["error"]["code"] == -32602
