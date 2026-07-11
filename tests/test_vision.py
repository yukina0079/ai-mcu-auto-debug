from __future__ import annotations

import builtins
import sys
from pathlib import Path

from ai_mcu_debug.vision import _classify_quality, analyze_board_image, capture_camera_image, scan_cameras


def test_camera_access_is_blocked_without_explicit_intent() -> None:
    scan = scan_cameras()
    capture = capture_camera_image()

    assert scan["status"] == "camera_blocked_by_policy"
    assert capture["status"] == "camera_blocked_by_policy"
    assert scan["policy"]["camera_allowed"] is False


def test_vision_reports_missing_opencv(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"not-an-image")
    original_import = builtins.__import__
    monkeypatch.delitem(sys.modules, "cv2", raising=False)

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cv2":
            raise ImportError("blocked for test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    report = analyze_board_image(image=image)

    assert report["status"] == "opencv_missing"
    assert ".[vision]" in report["next_actions"][0]


def test_quality_classification_is_deterministic() -> None:
    poor = _classify_quality(
        brightness=20,
        contrast=5,
        focus_score=10,
        dark_ratio=0.9,
        bright_ratio=0.0,
    )
    good = _classify_quality(
        brightness=120,
        contrast=45,
        focus_score=180,
        dark_ratio=0.1,
        bright_ratio=0.05,
    )

    assert poor["ok"] is False
    assert {"frame_too_dark", "low_contrast", "frame_may_be_blurry"} <= set(poor["warnings"])
    assert good == {"ok": True, "warnings": []}
