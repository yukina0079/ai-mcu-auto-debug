from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolCheck:
    name: str
    executable: str
    available: bool
    path: str | None
    version: str | None = None


DEFAULT_TOOL_CANDIDATES = {
    "target_gdb": ["arm-none-eabi-gdb", "riscv64-unknown-elf-gdb", "gdb-multiarch"],
    "host_gdb": ["gdb"],
    "openocd": ["openocd"],
    "pyocd": ["pyocd"],
    "jlink_gdb_server": ["JLinkGDBServerCL", "JLinkGDBServerCL.exe", "JLinkGDBServer", "JLinkGDBServer.exe"],
    "probe_rs": ["probe-rs"],
    "platformio": ["pio", "platformio"],
    "uv4": ["UV4.exe", "UV4"],
    "cmake": ["cmake"],
    "ninja": ["ninja"],
    "make": ["make"],
    "pytest": ["pytest"],
}


def run_doctor(debug_backend: str | None = None, build_backend: str | None = None) -> dict[str, object]:
    checks: list[ToolCheck] = []
    for name, executables in DEFAULT_TOOL_CANDIDATES.items():
        checks.append(_check_first_available(name, executables + _extra_tool_candidates(name)))
    available = {check.name: check.available for check in checks}
    recommendations = _recommendations(available, debug_backend=debug_backend, build_backend=build_backend)
    gates = _readiness_gates(available, debug_backend=debug_backend, build_backend=build_backend)
    return {
        "ok": all(gate["ok"] for gate in gates),
        "debug_backend": debug_backend,
        "build_backend": build_backend,
        "readiness_gates": gates,
        "checks": [check.__dict__ for check in checks],
        "recommendations": recommendations,
        "notes": [
            "At least one target GDB executable and one GDB server backend are needed for first-stage hardware debug.",
            "OpenOCD, J-Link GDB Server, pyOCD, or probe-rs GDB can be launched through debug.target.*.json server_command.",
        ],
    }


def _check_first_available(name: str, executables: list[str]) -> ToolCheck:
    for executable in executables:
        path = _resolve_executable(executable)
        if path:
            return ToolCheck(name=name, executable=Path(path).name, available=True, path=path, version=_read_version(path))
    return ToolCheck(name=name, executable=executables[0], available=False, path=None)


def _resolve_executable(executable: str) -> str | None:
    path = Path(executable)
    if path.is_absolute() and path.exists():
        return str(path)
    return shutil.which(executable)


def _read_version(path: str) -> str | None:
    for flag in ("--version", "-version", "-v"):
        try:
            completed = subprocess.run([path, flag], capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = (completed.stdout or completed.stderr).strip()
        if output:
            return output.splitlines()[0]
    return None


def _extra_tool_candidates(name: str) -> list[str]:
    if name == "target_gdb":
        return _glob_paths(Path.home() / "AppData/Roaming/xPacks", "**/arm-none-eabi-gdb.exe")
    if name == "openocd":
        candidates: list[str] = []
        local = Path.home() / "AppData/Local"
        candidates.extend(_glob_paths(local / "Microsoft/WinGet/Packages", "**/openocd.exe"))
        candidates.extend(_glob_paths(Path.home() / "AppData/Roaming/xPacks", "**/openocd.exe"))
        return candidates
    if name == "pyocd":
        return _glob_paths(Path.home() / "AppData/Roaming/Python", "**/pyocd.exe")
    return []


def _glob_paths(root: Path, pattern: str) -> list[str]:
    if not root.exists():
        return []
    return [str(path) for path in root.glob(pattern) if path.is_file()]


def _readiness_gates(
    available: dict[str, bool],
    debug_backend: str | None,
    build_backend: str | None,
) -> list[dict[str, object]]:
    gates: list[dict[str, object]] = []
    debug_tools = _required_debug_tools(debug_backend)
    for name in debug_tools:
        gates.append({"name": name, "ok": available.get(name, False), "kind": "debug"})
    for name in _required_build_tools(build_backend):
        gates.append({"name": name, "ok": available.get(name, False), "kind": "build"})
    if not gates:
        gates.append(
            {
                "name": "any_gdb_server_backend",
                "ok": available.get("target_gdb", False)
                and (
                    available.get("openocd", False)
                    or available.get("pyocd", False)
                    or available.get("jlink_gdb_server", False)
                    or available.get("probe_rs", False)
                ),
                "kind": "debug",
            }
        )
    return gates


def _required_debug_tools(debug_backend: str | None) -> list[str]:
    if debug_backend in {None, ""}:
        return []
    mapping = {
        "openocd-gdb": ["target_gdb", "openocd"],
        "pyocd-gdb": ["target_gdb", "pyocd"],
        "jlink-gdb": ["target_gdb", "jlink_gdb_server"],
        "probe-rs-gdb": ["target_gdb", "probe_rs"],
        "gdb-remote": ["target_gdb"],
    }
    return mapping.get(debug_backend, [])


def _required_build_tools(build_backend: str | None) -> list[str]:
    if build_backend in {None, "", "command"}:
        return []
    mapping = {
        "cmake": ["cmake"],
        "platformio": ["platformio"],
        "keil": ["uv4"],
    }
    return mapping.get(build_backend, [])


def _recommendations(
    available: dict[str, bool],
    debug_backend: str | None = None,
    build_backend: str | None = None,
) -> list[str]:
    recommendations: list[str] = []
    required_debug_tools = _required_debug_tools(debug_backend)
    if (not required_debug_tools and not available.get("target_gdb", False)) or (
        "target_gdb" in required_debug_tools and not available.get("target_gdb", False)
    ):
        recommendations.append("Install target GDB such as arm-none-eabi-gdb, riscv64-unknown-elf-gdb, or gdb-multiarch, then set debug.target.json gdb_path to it.")
    if debug_backend and any(not available.get(tool, False) for tool in required_debug_tools if tool != "target_gdb"):
        missing = [tool for tool in required_debug_tools if not available.get(tool, False)]
        recommendations.append(f"Install the required debug backend tool(s) for {debug_backend}: {', '.join(missing)}.")
    elif not debug_backend and not (
        available.get("openocd", False)
        or available.get("pyocd", False)
        or available.get("jlink_gdb_server", False)
        or available.get("probe_rs", False)
    ):
        recommendations.append("Install one GDB server backend: OpenOCD, pyOCD, SEGGER J-Link GDB Server, or probe-rs.")
    required_build_tools = _required_build_tools(build_backend)
    if build_backend and any(not available.get(tool, False) for tool in required_build_tools):
        missing = [tool for tool in required_build_tools if not available.get(tool, False)]
        recommendations.append(f"Install the required build tool(s) for {build_backend}: {', '.join(missing)}.")
    elif not build_backend and not available.get("cmake", False):
        recommendations.append("Install CMake or switch build.cmake.json to an existing build command.")
    if not available.get("pytest", False):
        recommendations.append("Install pytest or point smoke_test_command to an existing test runner.")
    if not recommendations:
        recommendations.append("Toolchain looks ready for first-stage hardware acceptance.")
    return recommendations
