from __future__ import annotations

import pytest

from ai_mcu_debug.adapters import GdbRemoteAdapter
from ai_mcu_debug.build import CMakeBuildAdapter, CommandBuildAdapter
from ai_mcu_debug.factory import create_build_adapter, create_debug_adapter
from ai_mcu_debug.models import BuildConfig, DebugTargetConfig


@pytest.mark.parametrize("backend", ["openocd-gdb", "pyocd-gdb", "jlink-gdb", "probe-rs-gdb"])
def test_gdb_server_debug_backends_share_gdb_remote_adapter(backend: str) -> None:
    adapter = create_debug_adapter(DebugTargetConfig(backend=backend, server_command=["gdb-server"]))

    assert isinstance(adapter, GdbRemoteAdapter)


def test_unknown_debug_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported debug backend"):
        create_debug_adapter(DebugTargetConfig(backend="made-up-debugger"))


def test_cmake_build_backend_uses_cmake_adapter() -> None:
    adapter = create_build_adapter(BuildConfig(backend="cmake"))

    assert isinstance(adapter, CMakeBuildAdapter)


@pytest.mark.parametrize("backend", ["command", "keil", "platformio"])
def test_command_style_build_backends_use_command_adapter(backend: str) -> None:
    adapter = create_build_adapter(BuildConfig(backend=backend, build_command=["build"]))

    assert isinstance(adapter, CommandBuildAdapter)


def test_unknown_build_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported build backend"):
        create_build_adapter(BuildConfig(backend="made-up-builder"))
