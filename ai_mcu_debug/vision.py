from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def scan_cameras(
    *,
    max_devices: int = 5,
    backend: str = "auto",
    allow_camera: bool = False,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Discover camera indexes without retaining frames."""

    if not allow_camera:
        return _finalize(_camera_blocked("camera scan"), output)
    if max_devices <= 0:
        return _finalize(
            {
                "ok": False,
                "status": "invalid_max_devices",
                "max_devices": max_devices,
                "next_actions": ["Use a positive max_devices value."],
            },
            output,
        )

    cv2, error = _load_cv2()
    if error:
        return _finalize(error, output)

    cameras: list[dict[str, Any]] = []
    for index in range(max_devices):
        capture = _open_capture(cv2, index, backend)
        try:
            if not capture.isOpened():
                continue
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            cameras.append(
                {
                    "index": index,
                    "width": int(width),
                    "height": int(height),
                    "backend": backend,
                }
            )
        finally:
            capture.release()

    return _finalize(
        {
            "ok": bool(cameras),
            "status": "ok" if cameras else "no_camera_detected",
            "source": "camera",
            "platform": platform.system(),
            "cameras": cameras,
            "policy": _camera_policy(allow_camera=True),
            "next_actions": [] if cameras else ["Connect or enable a camera, then retry with allow_camera=true."],
        },
        output,
    )


def capture_camera_image(
    *,
    camera_index: int = 0,
    image_output: str | Path = "debug_runs/vision/latest.jpg",
    report_output: str | Path | None = None,
    baseline: str | Path | None = None,
    width: int | None = None,
    height: int | None = None,
    warmup_frames: int = 5,
    backend: str = "auto",
    allow_camera: bool = False,
) -> dict[str, Any]:
    """Capture one board image and attach deterministic quality/change evidence."""

    if not allow_camera:
        return _finalize(_camera_blocked("camera capture"), report_output)
    if camera_index < 0 or warmup_frames < 0:
        return _finalize(
            {
                "ok": False,
                "status": "invalid_camera_options",
                "camera_index": camera_index,
                "warmup_frames": warmup_frames,
            },
            report_output,
        )

    cv2, error = _load_cv2()
    if error:
        return _finalize(error, report_output)

    capture = _open_capture(cv2, camera_index, backend)
    try:
        if not capture.isOpened():
            return _finalize(
                {
                    "ok": False,
                    "status": "camera_open_failed",
                    "camera_index": camera_index,
                    "backend": backend,
                    "policy": _camera_policy(allow_camera=True),
                },
                report_output,
            )
        if width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        frame = None
        for _ in range(warmup_frames + 1):
            ok, candidate = capture.read()
            if ok and candidate is not None:
                frame = candidate
        if frame is None:
            return _finalize(
                {
                    "ok": False,
                    "status": "camera_read_failed",
                    "camera_index": camera_index,
                    "backend": backend,
                    "policy": _camera_policy(allow_camera=True),
                },
                report_output,
            )
    finally:
        capture.release()

    image_path = Path(image_output)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(image_path), frame):
        return _finalize(
            {"ok": False, "status": "image_write_failed", "image_path": str(image_path)},
            report_output,
        )

    report = _analyze_frame(
        cv2,
        frame,
        image_path=image_path,
        baseline_path=Path(baseline) if baseline else None,
    )
    report.update(
        {
            "source": "camera",
            "camera_index": camera_index,
            "backend": backend,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "policy": _camera_policy(allow_camera=True),
        }
    )
    return _finalize(report, report_output)


def analyze_board_image(
    *,
    image: str | Path,
    baseline: str | Path | None = None,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Analyze an existing image and expose it for agent-side semantic inspection."""

    image_path = Path(image)
    if not image_path.exists():
        return _finalize(
            {"ok": False, "status": "image_missing", "image_path": str(image_path)},
            output,
        )
    cv2, error = _load_cv2()
    if error:
        return _finalize(error, output)
    frame = cv2.imread(str(image_path))
    if frame is None:
        return _finalize(
            {"ok": False, "status": "image_decode_failed", "image_path": str(image_path)},
            output,
        )
    report = _analyze_frame(
        cv2,
        frame,
        image_path=image_path,
        baseline_path=Path(baseline) if baseline else None,
    )
    report["source"] = "image_file"
    return _finalize(report, output)


def _analyze_frame(
    cv2: Any,
    frame: Any,
    *,
    image_path: Path,
    baseline_path: Path | None,
) -> dict[str, Any]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    brightness = float(gray.mean())
    contrast = float(gray.std())
    focus_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    dark_ratio = float((gray < 25).mean())
    bright_ratio = float((gray > 245).mean())
    quality = _classify_quality(
        brightness=brightness,
        contrast=contrast,
        focus_score=focus_score,
        dark_ratio=dark_ratio,
        bright_ratio=bright_ratio,
    )

    comparison: dict[str, Any] = {"status": "not_requested"}
    if baseline_path:
        comparison = _compare_baseline(cv2, frame, baseline_path)

    return {
        "ok": True,
        "status": "ok",
        "image_path": str(image_path),
        "mime_type": _mime_type(image_path),
        "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "width": int(width),
        "height": int(height),
        "metrics": {
            "brightness_mean": round(brightness, 3),
            "contrast_std": round(contrast, 3),
            "focus_score": round(focus_score, 3),
            "dark_pixel_ratio": round(dark_ratio, 6),
            "bright_pixel_ratio": round(bright_ratio, 6),
        },
        "quality": quality,
        "baseline_comparison": comparison,
        "semantic_analysis": {
            "status": "agent_inspection_required",
            "instruction": (
                "Inspect the returned image and correlate visible board/LED/display state with build, debug, "
                "serial, and knowledge evidence. Do not infer electrical correctness from appearance alone."
            ),
        },
    }


def _compare_baseline(cv2: Any, frame: Any, baseline_path: Path) -> dict[str, Any]:
    if not baseline_path.exists():
        return {"status": "baseline_missing", "baseline_path": str(baseline_path)}
    baseline = cv2.imread(str(baseline_path))
    if baseline is None:
        return {"status": "baseline_decode_failed", "baseline_path": str(baseline_path)}
    if baseline.shape[:2] != frame.shape[:2]:
        baseline = cv2.resize(baseline, (frame.shape[1], frame.shape[0]))
    difference = cv2.absdiff(frame, baseline)
    gray_difference = cv2.cvtColor(difference, cv2.COLOR_BGR2GRAY)
    mean_difference = float(gray_difference.mean()) / 255.0
    changed_ratio = float((gray_difference > 20).mean())
    return {
        "status": "changed" if changed_ratio >= 0.01 else "stable",
        "baseline_path": str(baseline_path),
        "mean_absolute_difference": round(mean_difference, 6),
        "changed_pixel_ratio": round(changed_ratio, 6),
        "threshold": 20,
    }


def _classify_quality(
    *,
    brightness: float,
    contrast: float,
    focus_score: float,
    dark_ratio: float,
    bright_ratio: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    if brightness < 35 or dark_ratio > 0.8:
        warnings.append("frame_too_dark")
    if brightness > 220 or bright_ratio > 0.8:
        warnings.append("frame_overexposed")
    if contrast < 12:
        warnings.append("low_contrast")
    if focus_score < 35:
        warnings.append("frame_may_be_blurry")
    return {"ok": not warnings, "warnings": warnings}


def _load_cv2() -> tuple[Any | None, dict[str, Any] | None]:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return None, {
            "ok": False,
            "status": "opencv_missing",
            "next_actions": ["Install the vision extra with: python -m pip install -e .[vision]"],
        }
    return cv2, None


def _open_capture(cv2: Any, index: int, backend: str) -> Any:
    backend_ids = {
        "dshow": getattr(cv2, "CAP_DSHOW", None),
        "msmf": getattr(cv2, "CAP_MSMF", None),
        "v4l2": getattr(cv2, "CAP_V4L2", None),
    }
    backend_id = backend_ids.get(backend.lower())
    return cv2.VideoCapture(index, backend_id) if backend_id is not None else cv2.VideoCapture(index)


def _camera_blocked(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "camera_blocked_by_policy",
        "policy": _camera_policy(allow_camera=False),
        "next_actions": [f"Set allow_camera=true only when {action} is intended for the current bench."],
    }


def _camera_policy(*, allow_camera: bool) -> dict[str, Any]:
    return {
        "camera_allowed": allow_camera,
        "captures_environment": True,
        "touches_target_state": False,
        "flash_allowed": False,
        "repair_allowed": False,
    }


def _mime_type(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def _finalize(report: dict[str, Any], output: str | Path | None) -> dict[str, Any]:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report["output"] = str(output_path)
    return report
