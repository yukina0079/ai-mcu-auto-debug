from __future__ import annotations

from .adapters import GdbRemoteAdapter
from .build import CMakeBuildAdapter, CommandBuildAdapter
from .interfaces import BuildAdapter, DebugAdapter, RepairAdapter
from .models import BuildConfig, DebugTargetConfig
from .repair import CommandRepairAdapter


def create_debug_adapter(config: DebugTargetConfig) -> DebugAdapter:
    if config.backend in {"gdb-remote", "openocd-gdb", "jlink-gdb", "pyocd-gdb", "probe-rs-gdb"}:
        return GdbRemoteAdapter(config)
    raise ValueError(f"Unsupported debug backend: {config.backend}")


def create_build_adapter(config: BuildConfig) -> BuildAdapter:
    if config.backend == "cmake":
        return CMakeBuildAdapter(config)
    if config.backend in {"command", "keil", "platformio", "esp-idf"}:
        return CommandBuildAdapter(config)
    raise ValueError(f"Unsupported build backend: {config.backend}")


def create_repair_adapter(config: BuildConfig) -> RepairAdapter | None:
    if not config.repair_command:
        return None
    return CommandRepairAdapter(config.repair_command, cwd=config.source_dir, timeout_s=config.repair_timeout_s)
