from ai_mcu_debug.diagnostics import analyze_debug_failure


def test_analyze_openocd_open_failed() -> None:
    analysis = analyze_debug_failure("", {"server_output_tail": ["Error: open failed"]})

    assert analysis["probable_causes"] == ["debug_probe_open_failed"]
    assert "Check that the ST-Link/J-Link/CMSIS-DAP probe is connected over USB." in analysis["next_actions"]


def test_analyze_swd_dp_not_responding() -> None:
    analysis = analyze_debug_failure(
        "Could not connect",
        {"server_output_tail": ["Info : CMSIS-DAP: Interface ready", "Error: Error connecting DP: cannot read IDR"]},
    )

    assert "swd_target_dp_not_responding" in analysis["probable_causes"]
    assert any("SWD target" in action for action in analysis["next_actions"])


def test_analyze_openocd_reset_line_held_low() -> None:
    analysis = analyze_debug_failure(
        "Could not connect",
        {
            "server_output_tail": [
                "Info : SWCLK/TCK = 1 SWDIO/TMS = 1 TDI = 1 TDO = 1 nTRST = 0 nRESET = 0",
                "Error: Error connecting DP: cannot read IDR",
            ]
        },
    )

    assert "target_reset_line_held_low" in analysis["probable_causes"]
    assert analysis["observations"]["openocd_reset_state"]["nRESET"] == 0
    assert any("NRST" in action for action in analysis["next_actions"])


def test_analyze_probe_already_open() -> None:
    analysis = analyze_debug_failure(
        "Could not connect",
        {"server_output_tail": ["0000741 C Error: already open [__main__]"]},
    )

    assert analysis["probable_causes"] == ["debug_probe_already_open"]
    assert any("other OpenOCD" in action for action in analysis["next_actions"])
