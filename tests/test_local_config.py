from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.local_config import write_detected_openocd_target


def test_write_detected_openocd_target(tmp_path: Path) -> None:
    report = {
        "checks": [
            {
                "name": "target_gdb",
                "available": True,
                "path": "C:/tools/arm-none-eabi-gdb.exe",
            },
            {
                "name": "openocd",
                "available": True,
                "path": "C:/tools/openocd.exe",
            },
        ]
    }
    output = tmp_path / "target.json"

    config = write_detected_openocd_target(
        output_path=output,
        executable="build/app.elf",
        interface_cfg="interface/stlink.cfg",
        target_cfg="target/stm32f1x.cfg",
        report=report,
    )

    assert config["gdb_path"] == "C:/tools/arm-none-eabi-gdb.exe"
    assert config["server_command"][0] == "C:/tools/openocd.exe"
    assert json.loads(output.read_text(encoding="utf-8")) == config
