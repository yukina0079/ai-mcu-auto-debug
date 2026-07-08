from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.doctor import run_doctor


CONFIG_DIR = Path(".embeddedskills")
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"


def init_workspace_config(
    output_dir: Path = CONFIG_DIR,
    project_path: Path = Path("."),
    chip: str | None = None,
    context_path: Path | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    build_config_path: Path | None = None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: Path | None = None,
    keil_target: str | None = None,
    uv4_path: Path | None = None,
    target_path: Path | None = None,
    task_path: Path | None = None,
    board: str | None = None,
    package_name: str | None = None,
    knowledge_repo_url: str | None = None,
    knowledge_repo_path: Path | None = None,
    debug_backend: str | None = None,
    executable_path: Path | None = None,
    interface_cfg: str | None = None,
    target_cfg: str | None = None,
    transport: str = "swd",
    adapter_speed: int = 100,
    generate_templates: bool = True,
    doctor_report: dict[str, Any] | None = None,
    probe_report: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = output_dir / CONFIG_FILE
    state_path = output_dir / STATE_FILE
    existing = _read_json(config_path) if config_path.exists() and not force else {}
    artifacts: list[dict[str, Any]] = []
    generated = _generate_missing_templates(
        output_dir=output_dir,
        project_path=project_path,
        chip=chip,
        context_path=context_path,
        build_config_path=build_config_path,
        build_backend=build_backend,
        pio_env=pio_env,
        keil_project=keil_project,
        keil_target=keil_target,
        uv4_path=uv4_path,
        target_path=target_path,
        task_path=task_path,
        debug_backend=debug_backend,
        executable_path=executable_path,
        interface_cfg=interface_cfg,
        target_cfg=target_cfg,
        transport=transport,
        adapter_speed=adapter_speed,
        generate_templates=generate_templates,
        force=force,
        doctor_report=doctor_report,
        probe_report=probe_report,
    )
    build_config_path = generated["build_config_path"]
    target_path = generated["target_path"]
    task_path = generated["task_path"]
    artifacts.extend(generated["artifacts"])
    config = _deep_merge(
        existing,
        {
            "schema_version": 1,
            "skill": {
                "name": "mcu-auto-debug",
                "runner": "python -m ai_mcu_debug.cli",
            },
            "project": _path(project_path),
            "mcu": _drop_none(
                {
                    "chip": chip,
                    "context": _path(context_path) if context_path else None,
                    "svd": _path(svd_path) if svd_path else None,
                    "linker": _path(linker_path) if linker_path else None,
                    "startup": _path(startup_path) if startup_path else None,
                    "board": board,
                    "package": package_name,
                }
            ),
            "build": _drop_none({"config": _path(build_config_path) if build_config_path else None}),
            "knowledge_repo": _drop_none(
                {
                    "url": knowledge_repo_url,
                    "local_path": _path(knowledge_repo_path) if knowledge_repo_path else None,
                }
            ),
            "debug": _drop_none(
                {
                    "backend": debug_backend,
                    "target": _path(target_path) if target_path else None,
                    "task": _path(task_path) if task_path else None,
                }
            ),
            "updated_at": _now(),
        },
    )
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    state = _read_json(state_path) if state_path.exists() and not force else {"schema_version": 1, "runs": []}
    state["updated_at"] = _now()
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "config": str(config_path), "state": str(state_path), "workspace": config, "artifacts": artifacts}


def load_workspace_defaults(config_path: Path = CONFIG_DIR / CONFIG_FILE) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    config = _read_json(config_path)
    mcu = config.get("mcu", {})
    build = config.get("build", {})
    debug = config.get("debug", {})
    knowledge_repo = config.get("knowledge_repo", {})
    return {
        "project": config.get("project"),
        "chip": mcu.get("chip"),
        "context": mcu.get("context"),
        "svd": mcu.get("svd"),
        "linker": mcu.get("linker"),
        "startup": mcu.get("startup"),
        "board": mcu.get("board"),
        "package": mcu.get("package"),
        "build_config": build.get("config"),
        "knowledge_repo_url": knowledge_repo.get("url"),
        "knowledge_repo_path": knowledge_repo.get("local_path"),
        "target": debug.get("target"),
        "task": debug.get("task"),
        "debug_backend": debug.get("backend"),
    }


def workspace_status(config_path: Path = CONFIG_DIR / CONFIG_FILE) -> dict[str, Any]:
    if not config_path.exists():
        return {
            "ok": False,
            "config": str(config_path),
            "reason": "workspace_config_missing",
            "next_actions": ["Run init-workspace with project/context/build/debug paths."],
        }
    defaults = load_workspace_defaults(config_path)
    checks = []
    for key in ("project", "context", "build_config", "target", "task"):
        value = defaults.get(key)
        checks.append(
            {
                "name": key,
                "path": value,
                "exists": Path(value).exists() if value else False,
                "required": key in {"project", "context", "build_config"},
            }
        )
    missing = [item for item in checks if item["required"] and not item["exists"]]
    return {
        "ok": not missing,
        "config": str(config_path),
        "defaults": defaults,
        "checks": checks,
        "missing": missing,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _generate_missing_templates(
    output_dir: Path,
    project_path: Path,
    chip: str | None,
    context_path: Path | None,
    build_config_path: Path | None,
    build_backend: str | None,
    pio_env: str | None,
    keil_project: Path | None,
    keil_target: str | None,
    uv4_path: Path | None,
    target_path: Path | None,
    task_path: Path | None,
    debug_backend: str | None,
    executable_path: Path | None,
    interface_cfg: str | None,
    target_cfg: str | None,
    transport: str,
    adapter_speed: int,
    generate_templates: bool,
    force: bool,
    doctor_report: dict[str, Any] | None,
    probe_report: dict[str, Any] | None,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    if not generate_templates:
        return {"build_config_path": build_config_path, "target_path": target_path, "task_path": task_path, "artifacts": artifacts}

    build_dir = _default_build_dir(project_path, chip)
    executable = executable_path or build_dir / "firmware.elf"
    if build_config_path is None:
        build_config_path = output_dir / "build.json"
        if force or not build_config_path.exists():
            _write_json(
                build_config_path,
                _build_config_template(
                    project_path,
                    build_dir,
                    executable,
                    context_path,
                    doctor_report,
                    build_backend=build_backend,
                    pio_env=pio_env,
                    keil_project=keil_project,
                    keil_target=keil_target,
                    uv4_path=uv4_path,
                ),
            )
            artifacts.append({"kind": "build_config", "path": str(build_config_path), "generated": True})

    if task_path is None:
        task_path = output_dir / "debug_task.json"
        if force or not task_path.exists():
            _write_json(task_path, _debug_task_template(context_path))
            artifacts.append({"kind": "debug_task", "path": str(task_path), "generated": True})

    backend = debug_backend or "openocd-gdb"
    if target_path is None and backend in {"openocd-gdb", "pyocd-gdb", "jlink-gdb", "probe-rs-gdb"}:
        target_path = output_dir / "debug.target.json"
        if force or not target_path.exists():
            if backend == "pyocd-gdb":
                target_template = _pyocd_target_template(
                    executable=executable,
                    chip=chip,
                    adapter_speed=adapter_speed,
                    doctor_report=doctor_report,
                )
            elif backend == "jlink-gdb":
                target_template = _jlink_target_template(
                    executable=executable,
                    chip=chip,
                    adapter_speed=adapter_speed,
                    doctor_report=doctor_report,
                )
            elif backend == "probe-rs-gdb":
                target_template = _probe_rs_target_template(
                    executable=executable,
                    chip=chip,
                    adapter_speed=adapter_speed,
                    doctor_report=doctor_report,
                )
            else:
                target_template = _openocd_target_template(
                    executable=executable,
                    interface_cfg=interface_cfg,
                    target_cfg=target_cfg or _infer_openocd_target_cfg(chip),
                    transport=transport,
                    adapter_speed=adapter_speed,
                    doctor_report=doctor_report,
                    probe_report=probe_report,
                )
            if target_template:
                _write_json(target_path, target_template)
                artifacts.append({"kind": "debug_target", "path": str(target_path), "generated": True})

    return {"build_config_path": build_config_path, "target_path": target_path, "task_path": task_path, "artifacts": artifacts}


def _build_config_template(
    project_path: Path,
    build_dir: Path,
    executable: Path,
    context_path: Path | None,
    doctor_report: dict[str, Any] | None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: Path | None = None,
    keil_target: str | None = None,
    uv4_path: Path | None = None,
) -> dict[str, Any]:
    backend = build_backend or _infer_build_backend(project_path)
    if backend == "platformio":
        return _platformio_build_template(project_path, pio_env)
    if backend == "keil":
        return _keil_build_template(project_path, keil_project, keil_target, uv4_path)
    if backend == "command":
        return _command_build_template(project_path)

    configure_command = ["cmake", "-S", str(project_path), "-B", str(build_dir), "-G", "Ninja"]
    toolchain = project_path / "arm-gcc-toolchain.cmake"
    if toolchain.exists():
        configure_command.append(f"-DCMAKE_TOOLCHAIN_FILE={toolchain.resolve()}")
        arm_gcc_bin = _arm_gcc_bin_from_doctor(doctor_report)
        if arm_gcc_bin:
            configure_command.append(f"-DARM_GCC_BIN={arm_gcc_bin}")
    linker = _linker_from_context(context_path)
    if linker:
        configure_command.append(f"-DLINKER_SCRIPT={linker}")
    return {
        "backend": "cmake",
        "source_dir": ".",
        "build_dir": str(build_dir),
        "configure_command": configure_command,
        "build_command": ["cmake", "--build", str(build_dir)],
        "flash_command": None,
        "smoke_test_command": ["python", "-m", "ai_mcu_debug.cli", "elf-check", "--elf", str(executable)],
        "runtime_log_command": None,
        "repair_command": None,
        "command_timeout_s": None,
        "runtime_log_timeout_s": 10,
        "repair_timeout_s": 600,
        "max_repair_iterations": 3,
        "extra": {},
    }


def _command_build_template(project_path: Path) -> dict[str, Any]:
    return {
        "backend": "command",
        "source_dir": str(project_path),
        "build_dir": "build",
        "configure_command": None,
        "build_command": None,
        "flash_command": None,
        "smoke_test_command": None,
        "runtime_log_command": None,
        "repair_command": None,
        "command_timeout_s": None,
        "runtime_log_timeout_s": 10,
        "repair_timeout_s": 600,
        "max_repair_iterations": 3,
        "extra": {},
    }


def _platformio_build_template(project_path: Path, pio_env: str | None) -> dict[str, Any]:
    env_args = ["-e", pio_env] if pio_env else []
    return {
        "backend": "platformio",
        "source_dir": str(project_path),
        "build_dir": ".pio/build",
        "configure_command": None,
        "build_command": ["pio", "run", *env_args],
        "flash_command": ["pio", "run", *env_args, "-t", "upload"],
        "smoke_test_command": None,
        "runtime_log_command": None,
        "repair_command": None,
        "command_timeout_s": None,
        "runtime_log_timeout_s": 10,
        "repair_timeout_s": 600,
        "max_repair_iterations": 3,
        "extra": _drop_none({"pio_env": pio_env}),
    }


def _keil_build_template(
    project_path: Path,
    keil_project: Path | None,
    keil_target: str | None,
    uv4_path: Path | None,
) -> dict[str, Any]:
    project_file = keil_project or _find_first(project_path, "*.uvprojx")
    uv4 = str(uv4_path or "UV4.exe")
    build_command = [uv4]
    if project_file:
        build_command.extend(["-b", str(project_file)])
    if keil_target:
        build_command.extend(["-t", keil_target])
    return {
        "backend": "keil",
        "source_dir": str(project_path),
        "build_dir": "build/keil",
        "configure_command": None,
        "build_command": build_command,
        "flash_command": None,
        "smoke_test_command": None,
        "runtime_log_command": None,
        "repair_command": None,
        "command_timeout_s": None,
        "runtime_log_timeout_s": 10,
        "repair_timeout_s": 600,
        "max_repair_iterations": 3,
        "extra": _drop_none(
            {
                "keil_project": str(project_file) if project_file else None,
                "keil_target": keil_target,
                "uv4": uv4,
            }
        ),
    }


def _arm_gcc_bin_from_doctor(doctor_report: dict[str, Any] | None) -> str | None:
    if not doctor_report:
        return None
    target_gdb = next((item for item in doctor_report.get("checks", []) if item.get("name") == "target_gdb"), None)
    path = target_gdb.get("path") if target_gdb else None
    if not path:
        return None
    return str(Path(path).parent)


def _linker_from_context(context_path: Path | None) -> str | None:
    if not context_path or not context_path.exists():
        return None
    context = _read_json(context_path)
    linker = context.get("sources", {}).get("linker")
    return str(Path(linker).resolve()) if linker else None


def _debug_task_template(context_path: Path | None) -> dict[str, Any]:
    memory_reads: list[dict[str, Any]] = []
    if context_path and context_path.exists():
        context = _read_json(context_path)
        ram = next((region for region in context.get("memory_regions", []) if region.get("name", "").upper() in {"RAM", "SRAM"}), None)
        if ram:
            memory_reads.append({"address": f"0x{int(ram['origin']):08X}", "length": 32})
    if not memory_reads:
        memory_reads.append({"address": "0x20000000", "length": 32})
    return {
        "name": "first_phase_debug",
        "breakpoints": ["main"],
        "registers": ["pc", "sp", "lr", "xpsr"],
        "memory_reads": memory_reads,
        "reset_before_run": True,
        "launch_from_vector_table": "0x08000000",
        "step_count": 1,
        "break_timeout_s": 10.0,
        "record_path": "debug_runs/task_records.jsonl",
    }


def _openocd_target_template(
    executable: Path,
    interface_cfg: str | None,
    target_cfg: str | None,
    transport: str,
    adapter_speed: int,
    doctor_report: dict[str, Any] | None,
    probe_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not target_cfg:
        return None
    selected_interface = interface_cfg or _infer_interface_cfg(probe_report)
    if not selected_interface:
        return None
    report = doctor_report or run_doctor()
    checks = {item["name"]: item for item in report.get("checks", [])}
    target_gdb = checks.get("target_gdb", {})
    openocd = checks.get("openocd", {})
    if not target_gdb.get("available") or not openocd.get("available"):
        return None
    server_command = [
        openocd["path"],
        "-f",
        selected_interface,
        "-c",
        f"transport select {transport}",
        "-f",
        target_cfg,
        "-c",
        f"adapter speed {adapter_speed}",
        "-c",
        "init; reset halt",
    ]
    return {
        "backend": "openocd-gdb",
        "executable": str(executable),
        "gdb_path": target_gdb["path"],
        "remote": "localhost:3333",
        "cwd": ".",
        "log_path": "debug_runs/debug_commands.jsonl",
        "server_command": server_command,
        "server_startup_delay_s": 2.0,
        "connect_retries": 5,
        "connect_retry_delay_s": 1.0,
        "recover_on_disconnect": True,
        "command_retries": 2,
    }


def _pyocd_target_template(
    executable: Path,
    chip: str | None,
    adapter_speed: int,
    doctor_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    report = doctor_report or run_doctor()
    checks = {item["name"]: item for item in report.get("checks", [])}
    target_gdb = checks.get("target_gdb", {})
    pyocd = checks.get("pyocd", {})
    if not target_gdb.get("available") or not pyocd.get("available"):
        return None
    server_command = [
        pyocd["path"],
        "gdbserver",
        "--port",
        "3333",
        "--frequency",
        str(max(1, adapter_speed) * 1000),
    ]
    pyocd_target = _infer_pyocd_target(chip)
    if pyocd_target:
        server_command.extend(["--target", pyocd_target])
    return {
        "backend": "pyocd-gdb",
        "executable": str(executable),
        "gdb_path": target_gdb["path"],
        "remote": "localhost:3333",
        "cwd": ".",
        "log_path": "debug_runs/debug_commands.jsonl",
        "server_command": server_command,
        "server_startup_delay_s": 2.0,
        "connect_retries": 5,
        "connect_retry_delay_s": 1.0,
        "recover_on_disconnect": True,
        "command_retries": 2,
    }


def _jlink_target_template(
    executable: Path,
    chip: str | None,
    adapter_speed: int,
    doctor_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not chip:
        return None
    report = doctor_report or run_doctor()
    checks = {item["name"]: item for item in report.get("checks", [])}
    target_gdb = checks.get("target_gdb", {})
    jlink = checks.get("jlink_gdb_server", {})
    if not target_gdb.get("available") or not jlink.get("available"):
        return None
    server_command = [
        jlink["path"],
        "-device",
        chip,
        "-if",
        "SWD",
        "-speed",
        str(max(1, adapter_speed)),
        "-port",
        "3333",
        "-nogui",
    ]
    return {
        "backend": "jlink-gdb",
        "executable": str(executable),
        "gdb_path": target_gdb["path"],
        "remote": "localhost:3333",
        "cwd": ".",
        "log_path": "debug_runs/debug_commands.jsonl",
        "server_command": server_command,
        "server_startup_delay_s": 2.0,
        "connect_retries": 5,
        "connect_retry_delay_s": 1.0,
        "recover_on_disconnect": True,
        "command_retries": 2,
    }


def _probe_rs_target_template(
    executable: Path,
    chip: str | None,
    adapter_speed: int,
    doctor_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not chip:
        return None
    report = doctor_report or run_doctor()
    checks = {item["name"]: item for item in report.get("checks", [])}
    target_gdb = checks.get("target_gdb", {})
    probe_rs = checks.get("probe_rs", {})
    if not target_gdb.get("available") or not probe_rs.get("available"):
        return None
    speed_khz = max(1, adapter_speed)
    server_command = [
        probe_rs["path"],
        "gdb",
        "--chip",
        chip,
        "--speed",
        str(speed_khz),
        "--port",
        "3333",
    ]
    return {
        "backend": "probe-rs-gdb",
        "executable": str(executable),
        "gdb_path": target_gdb["path"],
        "remote": "localhost:3333",
        "cwd": ".",
        "log_path": "debug_runs/debug_commands.jsonl",
        "server_command": server_command,
        "server_startup_delay_s": 2.0,
        "connect_retries": 5,
        "connect_retry_delay_s": 1.0,
        "recover_on_disconnect": True,
        "command_retries": 2,
    }


def _default_build_dir(project_path: Path, chip: str | None) -> Path:
    project_name = project_path.name or "firmware"
    if chip:
        chip_name = chip.lower()
        if project_name.lower().endswith("_blinky"):
            return Path("build") / f"{chip_name}_blinky"
        return Path("build") / f"{chip_name}_{project_name}"
    return Path("build") / project_name


def _infer_openocd_target_cfg(chip: str | None) -> str | None:
    if not chip:
        return None
    normalized = chip.lower()
    if normalized.startswith("stm32f10") or normalized.startswith("stm32f1"):
        return "target/stm32f1x.cfg"
    return None


def _infer_pyocd_target(chip: str | None) -> str | None:
    if not chip:
        return None
    normalized = chip.lower().replace("_", "").replace("-", "")
    if normalized.startswith("stm32f103") and len(normalized) >= len("stm32f103rc"):
        return normalized[: len("stm32f103rc")]
    if normalized.startswith("stm32f10") and len(normalized) >= len("stm32f10xx"):
        return normalized[:9]
    return normalized


def _infer_build_backend(project_path: Path) -> str:
    if (project_path / "CMakeLists.txt").exists():
        return "cmake"
    if (project_path / "platformio.ini").exists():
        return "platformio"
    if _find_first(project_path, "*.uvprojx"):
        return "keil"
    return "command"


def _find_first(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    return next(root.glob(pattern), None)


def _infer_interface_cfg(probe_report: dict[str, Any] | None) -> str | None:
    if not probe_report:
        return None
    text = json.dumps(probe_report, ensure_ascii=False).lower()
    if "cmsis-dap" in text or "daplink" in text or "vid_c251&pid_f001" in text:
        return "interface/cmsis-dap.cfg"
    if "st-link" in text or "stlink" in text:
        return "interface/stlink.cfg"
    if "j-link" in text or "jlink" in text:
        return "interface/jlink.cfg"
    return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _path(path: Path) -> str:
    return str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        elif value != {}:
            result[key] = value
    return result
