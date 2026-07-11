from __future__ import annotations

import json
import os
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
    esp_idf = discover_esp_idf()
    checks: list[ToolCheck] = []
    for name, executables in DEFAULT_TOOL_CANDIDATES.items():
        checks.append(_check_first_available(name, executables + _extra_tool_candidates(name)))
    checks.extend(_esp_idf_tool_checks(esp_idf))
    available = {check.name: check.available for check in checks}
    recommendations = _recommendations(available, debug_backend=debug_backend, build_backend=build_backend)
    gates = _readiness_gates(available, debug_backend=debug_backend, build_backend=build_backend)
    return {
        "ok": all(gate["ok"] for gate in gates),
        "debug_backend": debug_backend,
        "build_backend": build_backend,
        "esp_idf": esp_idf,
        "readiness_gates": gates,
        "checks": [check.__dict__ for check in checks],
        "recommendations": recommendations,
        "notes": [
            "At least one target GDB executable and one GDB server backend are needed for first-stage hardware debug.",
            "OpenOCD, J-Link GDB Server, pyOCD, or probe-rs GDB can be launched through debug.target.*.json server_command.",
            "ESP-IDF installations managed by EIM/VS Code are discovered without requiring global PATH changes.",
        ],
    }


def discover_esp_idf(eim_config_path: str | Path | None = None) -> dict[str, object]:
    """Discover the selected ESP-IDF installation written by EIM/VS Code."""

    candidates: list[Path] = []
    if eim_config_path:
        candidates.append(Path(eim_config_path))
    tools_env = os.environ.get("IDF_TOOLS_PATH")
    if tools_env:
        candidates.append(Path(tools_env) / "eim_idf.json")
    if os.name == "nt":
        candidates.append(Path("C:/Espressif/tools/eim_idf.json"))
    candidates.append(Path.home() / ".espressif" / "eim_idf.json")

    config_path = next((path for path in candidates if path.exists()), None)
    if not config_path:
        return {"ok": False, "status": "not_found", "config": None}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "config_invalid", "config": str(config_path), "error": str(exc)}

    installs = [item for item in config.get("idfInstalled", []) if isinstance(item, dict)]
    selected_id = config.get("idfSelectedId")
    selected = next((item for item in installs if item.get("id") == selected_id), None)
    if selected is None and installs:
        selected = installs[0]
    if selected is None:
        return {"ok": False, "status": "no_selected_installation", "config": str(config_path)}

    idf_path = Path(str(selected.get("path") or ""))
    tools_path = Path(str(selected.get("idfToolsPath") or config_path.parent))
    python = Path(str(selected.get("python") or ""))
    activation_script = Path(str(selected.get("activationScript") or ""))
    idf_py = idf_path / "tools" / "idf.py"
    riscv_gdb = _first_file(tools_path, "riscv32-esp-elf-gdb/**/bin/riscv32-esp-elf-gdb.exe")
    openocd = _first_file(tools_path, "openocd-esp32/**/bin/openocd.exe")
    openocd_scripts = _first_directory(tools_path, "openocd-esp32/**/share/openocd/scripts")
    required = [idf_path, tools_path, python, activation_script, idf_py, riscv_gdb, openocd, openocd_scripts]
    ok = all(path is not None and path.exists() for path in required)
    return {
        "ok": ok,
        "status": "ready" if ok else "installation_incomplete",
        "config": str(config_path),
        "id": selected.get("id"),
        "version": selected.get("name"),
        "idf_path": str(idf_path),
        "tools_path": str(tools_path),
        "python": str(python),
        "activation_script": str(activation_script),
        "idf_py": str(idf_py),
        "riscv_gdb": str(riscv_gdb) if riscv_gdb else None,
        "openocd": str(openocd) if openocd else None,
        "openocd_scripts": str(openocd_scripts) if openocd_scripts else None,
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


def _read_version_command(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else None


def _esp_idf_tool_checks(discovery: dict[str, object]) -> list[ToolCheck]:
    def check(name: str, key: str, version_command: list[str] | None = None) -> ToolCheck:
        value = discovery.get(key)
        path = Path(str(value)) if value else None
        available = bool(path and path.exists())
        version = _read_version_command(version_command) if available and version_command else (_read_version(str(path)) if available else None)
        return ToolCheck(
            name=name,
            executable=path.name if path else key,
            available=available,
            path=str(path) if available else None,
            version=version,
        )

    python = str(discovery.get("python") or "")
    idf_py = str(discovery.get("idf_py") or "")
    return [
        check("idf_py", "idf_py", [python, idf_py, "--version"] if python and idf_py else None),
        check("esp_riscv_gdb", "riscv_gdb"),
        check("openocd_esp32", "openocd"),
    ]


def _first_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    return next((path for path in root.glob(pattern) if path.is_file()), None)


def _first_directory(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    return next((path for path in root.glob(pattern) if path.is_dir()), None)


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
                "ok": (
                    available.get("target_gdb", False)
                    and (
                        available.get("openocd", False)
                        or available.get("pyocd", False)
                        or available.get("jlink_gdb_server", False)
                        or available.get("probe_rs", False)
                    )
                )
                or (available.get("esp_riscv_gdb", False) and available.get("openocd_esp32", False)),
                "kind": "debug",
            }
        )
    return gates


def _required_debug_tools(debug_backend: str | None) -> list[str]:
    if debug_backend in {None, ""}:
        return []
    mapping = {
        "openocd-gdb": ["target_gdb", "openocd"],
        "esp-idf-openocd-gdb": ["esp_riscv_gdb", "openocd_esp32"],
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
        "esp-idf": ["idf_py"],
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
    any_target_gdb = available.get("target_gdb", False) or available.get("esp_riscv_gdb", False)
    if (not required_debug_tools and not any_target_gdb) or (
        "target_gdb" in required_debug_tools and not available.get("target_gdb", False)
    ):
        recommendations.append("Install target GDB such as arm-none-eabi-gdb, riscv64-unknown-elf-gdb, or gdb-multiarch, then set debug.target.json gdb_path to it.")
    if debug_backend and any(not available.get(tool, False) for tool in required_debug_tools if tool != "target_gdb"):
        missing = [tool for tool in required_debug_tools if not available.get(tool, False)]
        recommendations.append(f"Install the required debug backend tool(s) for {debug_backend}: {', '.join(missing)}.")
    elif not debug_backend and not (
        available.get("openocd", False)
        or available.get("openocd_esp32", False)
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
