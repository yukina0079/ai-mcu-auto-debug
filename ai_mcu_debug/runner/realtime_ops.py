from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_mcu_debug.interfaces import DebugAdapter


def execute_debug_operation(adapter: DebugAdapter, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    if operation == "halt":
        adapter.halt()
        return {"ok": True, "operation": operation}
    if operation == "resume":
        adapter.resume()
        return {"ok": True, "operation": operation}
    if operation == "wait-for-stop":
        output = adapter.wait_for_stop(float(params.get("timeout_s", 10.0)))
        return {"ok": True, "operation": operation, "output": output}
    if operation == "step":
        adapter.step()
        return {"ok": True, "operation": operation}
    if operation == "reset":
        adapter.reset(halt=bool(params.get("halt", True)))
        return {"ok": True, "operation": operation}
    if operation == "set-breakpoint":
        breakpoint = adapter.set_breakpoint(str(_require(params, "location")))
        return {"ok": True, "operation": operation, "breakpoint": asdict(breakpoint)}
    if operation == "delete-breakpoint":
        adapter.delete_breakpoint(str(_require(params, "breakpoint_id")))
        return {"ok": True, "operation": operation}
    if operation == "read-register":
        mapped = params.get("mapped_register")
        if isinstance(mapped, dict):
            address = _int_param(_require(mapped, "address"))
            size = int(mapped.get("size_bytes") or 4)
            block = adapter.read_memory(address, size)
            value = int.from_bytes(block.data[:size], "little")
            return {
                "ok": True,
                "operation": operation,
                "register": mapped.get("qualified_name") or params.get("register"),
                "address": f"0x{address:x}",
                "value": f"0x{value:x}",
                "data_hex": block.data.hex(),
            }
        value = adapter.read_register(str(_require(params, "register")))
        return {"ok": True, "operation": operation, "register": value.name, "value": f"0x{value.value:x}"}
    if operation == "write-register":
        adapter.write_register(str(_require(params, "register")), _int_param(_require(params, "value")))
        return {"ok": True, "operation": operation}
    if operation == "read-memory":
        block = adapter.read_memory(_int_param(_require(params, "address")), int(_require(params, "length")))
        return {
            "ok": True,
            "operation": operation,
            "address": f"0x{block.address:x}",
            "data_hex": block.data.hex(),
        }
    if operation == "write-memory":
        adapter.write_memory(_int_param(_require(params, "address")), bytes.fromhex(str(_require(params, "data_hex"))))
        return {"ok": True, "operation": operation}
    raise ValueError(f"Unsupported debug operation: {operation}")


def _int_param(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def _require(params: dict[str, Any], key: str) -> Any:
    value = params.get(key)
    if value is None:
        raise ValueError(f"Missing required parameter: {key}")
    return value
