from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def parse_svd(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    device: dict[str, Any] = {
        "name": _text(root, "name") or path.stem,
        "description": _text(root, "description"),
        "cpu": _parse_cpu(root.find("cpu")),
        "peripherals": [],
    }
    peripherals = root.find("peripherals")
    if peripherals is None:
        return device

    for peripheral in peripherals.findall("peripheral"):
        base_address = _int_text(peripheral, "baseAddress")
        peripheral_name = _text(peripheral, "name") or "UNKNOWN"
        item = {
            "name": peripheral_name,
            "description": _text(peripheral, "description"),
            "base_address": base_address,
            "source": str(path),
            "registers": [],
        }
        registers = peripheral.find("registers")
        if registers is not None:
            for register in registers.findall("register"):
                item["registers"].append(_parse_register(register, peripheral_name, base_address, path))
        device["peripherals"].append(item)
    return device


def _parse_cpu(node: ET.Element | None) -> dict[str, Any]:
    if node is None:
        return {}
    return {
        "name": _text(node, "name"),
        "revision": _text(node, "revision"),
        "endian": _text(node, "endian"),
        "mpu_present": _text(node, "mpuPresent"),
        "fpu_present": _text(node, "fpuPresent"),
        "nvic_prio_bits": _int_text(node, "nvicPrioBits"),
    }


def _parse_register(node: ET.Element, peripheral_name: str, base_address: int, path: Path) -> dict[str, Any]:
    offset = _int_text(node, "addressOffset")
    name = _text(node, "name") or "UNKNOWN"
    register = {
        "name": name,
        "qualified_name": f"{peripheral_name}.{name}",
        "description": _text(node, "description"),
        "address_offset": offset,
        "address": base_address + offset,
        "size": _int_text(node, "size"),
        "access": _text(node, "access"),
        "reset_value": _int_text(node, "resetValue"),
        "source": str(path),
        "fields": [],
    }
    fields = node.find("fields")
    if fields is not None:
        for field in fields.findall("field"):
            register["fields"].append(_parse_field(field))
    return register


def _parse_field(node: ET.Element) -> dict[str, Any]:
    bit_offset = _int_text(node, "bitOffset")
    bit_width = _int_text(node, "bitWidth")
    bit_range = _text(node, "bitRange")
    if bit_range:
        bit_offset, bit_width = _parse_bit_range(bit_range)
    return {
        "name": _text(node, "name"),
        "description": _text(node, "description"),
        "bit_offset": bit_offset,
        "bit_width": bit_width,
        "access": _text(node, "access"),
    }


def _parse_bit_range(value: str) -> tuple[int, int]:
    match = re.match(r"\[(\d+):(\d+)\]", value.strip())
    if not match:
        return 0, 0
    high = int(match.group(1))
    low = int(match.group(2))
    return low, high - low + 1


def _text(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    return " ".join(child.text.split())


def _int_text(node: ET.Element, tag: str) -> int:
    value = _text(node, tag)
    if not value:
        return 0
    return int(value.replace("#", "0x"), 0)
