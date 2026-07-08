from ai_mcu_debug.probe_scan import _classify_device, _recommendations


def test_classify_stlink_device() -> None:
    result = _classify_device(
        {
            "FriendlyName": "ST-Link Debug",
            "InstanceId": "USB\\VID_0483&PID_3748",
            "Class": "USB",
            "Status": "OK",
        }
    )

    assert result["matched"] is True
    assert "st-link" in result["matched_keywords"]


def test_classify_daplink_vid_pid_device() -> None:
    result = _classify_device(
        {
            "FriendlyName": "USB Serial Device (COM3)",
            "InstanceId": "USB\\VID_C251&PID_F001&MI_00\\8&16D6494D&0&0000",
            "Class": "Ports",
            "Status": "OK",
        }
    )

    assert result["matched"] is True
    assert result["matched_usb_ids"] == ["CMSIS-DAP/DAPLink compatible probe"]


def test_recommendations_when_no_probe_found() -> None:
    recommendations = _recommendations([])

    assert recommendations[0] == "No known debug probe detected in present USB/PnP devices."
