from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run safe first-stage MCU debug acceptance.")
    parser.add_argument("--report-dir", default="debug_runs/first_stage_acceptance")
    parser.add_argument("--target", default=".embeddedskills/debug.target.json")
    parser.add_argument("--connection-diagnostic-timeout-s", type=float, default=8.0)
    parser.add_argument("--skip-ai-debug", action="store_true", help="Run only host/probe/config checks.")
    args = parser.parse_args()

    runner = sys.executable
    commands = [
        [runner, "-m", "ai_mcu_debug.cli", "workspace-status"],
        [runner, "-m", "ai_mcu_debug.cli", "probe-scan"],
        [runner, "-m", "ai_mcu_debug.cli", "validate-target", "--target", args.target, "--scan-probes"],
    ]
    if not args.skip_ai_debug:
        commands.append(
            [
                runner,
                "-m",
                "ai_mcu_debug.cli",
                "ai-debug",
                "--mode",
                "read-only",
                "--target",
                args.target,
                "--report-dir",
                args.report_dir,
                "--connection-diagnostic-timeout-s",
                str(args.connection_diagnostic_timeout_s),
            ]
        )

    Path(args.report_dir).mkdir(parents=True, exist_ok=True)
    failed = False
    for command in commands:
        print(f"+ {' '.join(command)}", flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            failed = True
            break
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
