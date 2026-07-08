from ai_mcu_debug.adapters.gdb_remote import _parse_hex_value, _parse_memory_bytes


def test_parse_hex_value() -> None:
    assert _parse_hex_value('~"$1 = 0x08000100\\n"') == 0x08000100


def test_parse_memory_bytes() -> None:
    assert _parse_memory_bytes('^done,memory=[{begin="0x20000000",contents="0102ff"}]') == b"\x01\x02\xff"
