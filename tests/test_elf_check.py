from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.elf_check import check_elf


def test_check_elf_rejects_missing_file(tmp_path: Path) -> None:
    report = check_elf(tmp_path / "missing.elf")

    assert report["ok"] is False


def test_check_elf_accepts_minimal_elf_header(tmp_path: Path) -> None:
    elf = tmp_path / "firmware.elf"
    header = bytearray(52)
    header[0:4] = b"\x7fELF"
    header[4] = 1
    header[5] = 1
    header[18:20] = (40).to_bytes(2, "little")
    header[24:28] = (0x08000040).to_bytes(4, "little")
    elf.write_bytes(bytes(header))

    report = check_elf(elf)

    assert report["ok"] is True
    assert report["class"] == "ELF32"
    assert report["machine"] == 40
    assert report["entry"] == "0x8000040"
