from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.workspace import init_workspace_config, load_workspace_defaults, workspace_status


def test_init_workspace_config_writes_config_and_state(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "project"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text("{}", encoding="utf-8")
    build_config = tmp_path / "build.json"
    build_config.write_text("{}", encoding="utf-8")

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        chip="STM32F103RCT6",
        context_path=context,
        build_config_path=build_config,
        target_path=tmp_path / "target.json",
        task_path=tmp_path / "task.json",
        knowledge_repo_url="https://github.com/example/mcu-docs.git",
        knowledge_repo_path=tmp_path / "knowledge_repos" / "mcu-docs",
        debug_backend="openocd-gdb",
    )

    assert report["ok"] is True
    assert (config_dir / "config.json").exists()
    assert (config_dir / "state.json").exists()
    defaults = load_workspace_defaults(config_dir / "config.json")
    assert defaults["project"] == str(project)
    assert defaults["chip"] == "STM32F103RCT6"
    assert defaults["context"] == str(context)
    assert defaults["build_config"] == str(build_config)
    assert defaults["knowledge_repo_url"] == "https://github.com/example/mcu-docs.git"
    assert defaults["knowledge_repo_path"] == str(tmp_path / "knowledge_repos" / "mcu-docs")
    assert defaults["debug_backend"] == "openocd-gdb"


def test_workspace_status_reports_missing_config(tmp_path: Path) -> None:
    report = workspace_status(tmp_path / ".embeddedskills/config.json")

    assert report["ok"] is False
    assert report["reason"] == "workspace_config_missing"


def test_workspace_status_checks_required_paths(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "project"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text("{}", encoding="utf-8")
    build_config = tmp_path / "build.json"
    build_config.write_text("{}", encoding="utf-8")
    init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        context_path=context,
        build_config_path=build_config,
    )

    report = workspace_status(config_dir / "config.json")

    assert report["ok"] is True
    required = {item["name"]: item for item in report["checks"] if item["required"]}
    assert required["project"]["exists"] is True
    assert required["context"]["exists"] is True
    assert required["build_config"]["exists"] is True


def test_init_workspace_generates_templates_when_paths_are_missing(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "stm32f103_blinky"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text(
        '{"memory_regions":[{"name":"RAM","origin":536870912,"length":49152,"end":536920064}]}',
        encoding="utf-8",
    )
    doctor_report = {
        "checks": [
            {"name": "target_gdb", "available": True, "path": "C:/tools/arm-none-eabi-gdb.exe"},
            {"name": "openocd", "available": True, "path": "C:/tools/openocd.exe"},
        ]
    }
    probe_report = {"probes": [{"matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"]}]}

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        chip="STM32F103RCT6",
        context_path=context,
        doctor_report=doctor_report,
        probe_report=probe_report,
        force=True,
    )

    defaults = load_workspace_defaults(config_dir / "config.json")
    assert defaults["build_config"] == str(config_dir / "build.json")
    assert defaults["target"] == str(config_dir / "debug.target.json")
    assert defaults["task"] == str(config_dir / "debug_task.json")
    assert {item["kind"] for item in report["artifacts"]} == {"build_config", "debug_task", "debug_target"}
    assert "interface/cmsis-dap.cfg" in (config_dir / "debug.target.json").read_text(encoding="utf-8")
    assert "init; reset halt" in (config_dir / "debug.target.json").read_text(encoding="utf-8")
    assert "0x20000000" in (config_dir / "debug_task.json").read_text(encoding="utf-8")


def test_init_workspace_can_generate_pyocd_target_template(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "stm32f103_blinky"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text(
        '{"memory_regions":[{"name":"RAM","origin":536870912,"length":49152,"end":536920064}]}',
        encoding="utf-8",
    )
    doctor_report = {
        "checks": [
            {"name": "target_gdb", "available": True, "path": "C:/tools/arm-none-eabi-gdb.exe"},
            {"name": "pyocd", "available": True, "path": "C:/tools/pyocd.exe"},
        ]
    }

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        chip="STM32F103RCT6",
        context_path=context,
        debug_backend="pyocd-gdb",
        doctor_report=doctor_report,
        force=True,
    )

    defaults = load_workspace_defaults(config_dir / "config.json")
    target = (config_dir / "debug.target.json").read_text(encoding="utf-8")
    assert defaults["debug_backend"] == "pyocd-gdb"
    assert {"build_config", "debug_task", "debug_target"} == {item["kind"] for item in report["artifacts"]}
    assert '"backend": "pyocd-gdb"' in target
    assert '"--target"' in target
    assert '"stm32f103rc"' in target


def test_init_workspace_can_generate_jlink_target_template(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "stm32f103_blinky"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text(
        '{"memory_regions":[{"name":"RAM","origin":536870912,"length":49152,"end":536920064}]}',
        encoding="utf-8",
    )
    doctor_report = {
        "checks": [
            {"name": "target_gdb", "available": True, "path": "C:/tools/arm-none-eabi-gdb.exe"},
            {"name": "jlink_gdb_server", "available": True, "path": "C:/tools/JLinkGDBServerCL.exe"},
        ]
    }

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        chip="STM32F103RCT6",
        context_path=context,
        debug_backend="jlink-gdb",
        doctor_report=doctor_report,
        force=True,
    )

    defaults = load_workspace_defaults(config_dir / "config.json")
    target = (config_dir / "debug.target.json").read_text(encoding="utf-8")
    assert defaults["debug_backend"] == "jlink-gdb"
    assert {"build_config", "debug_task", "debug_target"} == {item["kind"] for item in report["artifacts"]}
    assert '"backend": "jlink-gdb"' in target
    assert '"-device"' in target
    assert '"STM32F103RCT6"' in target


def test_init_workspace_can_generate_probe_rs_target_template(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "stm32f103_blinky"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text(
        '{"memory_regions":[{"name":"RAM","origin":536870912,"length":49152,"end":536920064}]}',
        encoding="utf-8",
    )
    doctor_report = {
        "checks": [
            {"name": "target_gdb", "available": True, "path": "C:/tools/arm-none-eabi-gdb.exe"},
            {"name": "probe_rs", "available": True, "path": "C:/tools/probe-rs.exe"},
        ]
    }

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        chip="STM32F103RCT6",
        context_path=context,
        debug_backend="probe-rs-gdb",
        doctor_report=doctor_report,
        force=True,
    )

    defaults = load_workspace_defaults(config_dir / "config.json")
    target = (config_dir / "debug.target.json").read_text(encoding="utf-8")
    assert defaults["debug_backend"] == "probe-rs-gdb"
    assert {"build_config", "debug_task", "debug_target"} == {item["kind"] for item in report["artifacts"]}
    assert '"backend": "probe-rs-gdb"' in target
    assert '"gdb"' in target
    assert '"--chip"' in target


def test_init_workspace_can_generate_platformio_build_template(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "pio_project"
    project.mkdir()
    (project / "platformio.ini").write_text("[env:bluepill]\n", encoding="utf-8")
    context = tmp_path / "context.json"
    context.write_text("{}", encoding="utf-8")

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        context_path=context,
        build_backend="platformio",
        pio_env="bluepill",
    )

    build = (config_dir / "build.json").read_text(encoding="utf-8")
    assert "platformio" in build
    assert '"pio_env": "bluepill"' in build
    assert '"pio"' in build
    assert report["ok"] is True


def test_init_workspace_can_generate_keil_build_template(tmp_path: Path) -> None:
    config_dir = tmp_path / ".embeddedskills"
    project = tmp_path / "keil_project"
    project.mkdir()
    uvprojx = project / "app.uvprojx"
    uvprojx.write_text("<Project />", encoding="utf-8")
    context = tmp_path / "context.json"
    context.write_text("{}", encoding="utf-8")

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        context_path=context,
        build_backend="keil",
        keil_project=uvprojx,
        keil_target="Target 1",
        uv4_path=tmp_path / "UV4.exe",
    )

    build = (config_dir / "build.json").read_text(encoding="utf-8")
    assert '"backend": "keil"' in build
    assert "app.uvprojx" in build
    assert "Target 1" in build
    assert report["ok"] is True


def test_init_workspace_generates_esp_idf_supermini_templates(tmp_path: Path) -> None:
    project = tmp_path / "esp32c3_supermini_smoke"
    project.mkdir()
    (project / "CMakeLists.txt").write_text(
        "include($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(supermini_smoke)\n",
        encoding="utf-8",
    )
    tools = tmp_path / "tools"
    activation = tools / "PowerShell_profile.ps1"
    gdb = tools / "riscv32-esp-elf-gdb.exe"
    openocd = tools / "openocd.exe"
    scripts = tools / "openocd-scripts"
    for path in (activation, gdb, openocd):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    scripts.mkdir()
    doctor_report = {
        "esp_idf": {
            "ok": True,
            "activation_script": str(activation),
            "riscv_gdb": str(gdb),
            "openocd": str(openocd),
            "openocd_scripts": str(scripts),
        },
        "checks": [],
    }
    probe_report = {
        "probes": [
            {
                "matched_usb_ids": ["Espressif USB Serial/JTAG"],
                "friendly_name": "USB Serial Device (COM13)",
                "instance_id": "USB\\VID_303A&PID_1001&MI_00\\TEST",
            }
        ]
    }
    config_dir = tmp_path / ".embeddedskills"

    report = init_workspace_config(
        output_dir=config_dir,
        project_path=project,
        chip="ESP32C3",
        build_backend="esp-idf",
        debug_backend="esp-idf-openocd-gdb",
        doctor_report=doctor_report,
        probe_report=probe_report,
        force=True,
    )

    build = (config_dir / "build.json").read_text(encoding="utf-8")
    target = (config_dir / "debug.target.json").read_text(encoding="utf-8")
    task = (config_dir / "debug_task.json").read_text(encoding="utf-8")
    assert report["ok"] is True
    assert '"backend": "esp-idf"' in build
    assert "PowerShell_profile.ps1" in build
    assert "COM13" in build
    assert "supermini_smoke.elf" in target
    assert "board/esp32c3-builtin.cfg" in target
    assert "riscv32-esp-elf-gdb.exe" in target
    assert '"registers": [' in task
    assert '"ra"' in task
    assert '"launch_from_vector_table": null' in task
