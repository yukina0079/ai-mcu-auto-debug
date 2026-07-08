from __future__ import annotations

from pathlib import Path


def check_elf(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"ok": False, "elf": str(path), "error": "ELF file does not exist."}
    data = path.read_bytes()
    if len(data) < 52:
        return {"ok": False, "elf": str(path), "error": "ELF file is too small."}
    if data[:4] != b"\x7fELF":
        return {"ok": False, "elf": str(path), "error": "File does not have ELF magic."}
    elf_class = {1: "ELF32", 2: "ELF64"}.get(data[4], f"unknown:{data[4]}")
    endian = {1: "little", 2: "big"}.get(data[5], f"unknown:{data[5]}")
    machine = int.from_bytes(data[18:20], "little" if data[5] == 1 else "big")
    entry = int.from_bytes(data[24:28], "little" if data[5] == 1 else "big")
    return {
        "ok": True,
        "elf": str(path),
        "size_bytes": len(data),
        "class": elf_class,
        "endian": endian,
        "machine": machine,
        "entry": f"0x{entry:x}",
    }
