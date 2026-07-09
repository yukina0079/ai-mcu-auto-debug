from __future__ import annotations

import builtins
import json
import sys
from types import SimpleNamespace

from ai_mcu_debug.serial_log import collect_serial_log


def test_serial_log_reports_invalid_duration() -> None:
    report = collect_serial_log(port="COM_TEST", duration_s=0)

    assert report["ok"] is False
    assert report["status"] == "invalid_duration"


def test_serial_log_reports_missing_pyserial(monkeypatch) -> None:
    original_import = builtins.__import__
    monkeypatch.delitem(sys.modules, "serial", raising=False)

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "serial":
            raise ImportError("blocked for test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    report = collect_serial_log(port="COM_TEST", duration_s=0.01)

    assert report["ok"] is False
    assert report["status"] == "pyserial_missing"
    assert "pyserial" in report["next_actions"][0]


def test_serial_log_collects_lines_with_fake_serial(monkeypatch, tmp_path) -> None:
    class FakeSerial:
        def __init__(self, *args, **kwargs) -> None:
            self._chunks = [b"BOOT OK\n", b"TEST PASS\n"]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def readline(self) -> bytes:
            if self._chunks:
                return self._chunks.pop(0)
            return b""

    output = tmp_path / "serial.json"
    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=FakeSerial))

    report = collect_serial_log(port="COM_TEST", duration_s=0.01, output=output)

    assert report["ok"] is True
    assert report["lines"][:2] == ["BOOT OK", "TEST PASS"]
    assert report["observations"][:2] == ["BOOT OK", "TEST PASS"]
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ok"
