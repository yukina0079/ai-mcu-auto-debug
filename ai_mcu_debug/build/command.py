from __future__ import annotations

import re
import subprocess

from ai_mcu_debug.audit_log import append_audit_event, tail_text
from ai_mcu_debug.interfaces import BuildAdapter
from ai_mcu_debug.models import BuildConfig, BuildResult, RuntimeLogResult, SmokeTestResult


class CommandBuildAdapter(BuildAdapter):
    """Backend-neutral wrapper around existing build, flash, test, and log CLIs."""

    def __init__(self, config: BuildConfig) -> None:
        self.config = config

    def build(self) -> BuildResult:
        if self.config.configure_command:
            configure = run_command(
                self.config.configure_command,
                self.config.source_dir,
                event="configure_command",
                timeout_s=self.config.command_timeout_s,
            )
            if not configure.ok:
                return configure
        if not self.config.build_command:
            return _no_build_command(self.config.source_dir)
        return run_command(
            self.config.build_command,
            self.config.source_dir,
            event="build_command",
            timeout_s=self.config.command_timeout_s,
        )

    def flash(self) -> BuildResult:
        if not self.config.flash_command:
            result = BuildResult(
                ok=True,
                command=[],
                stdout="No flash command configured.",
                stderr="",
                returncode=0,
            )
            append_audit_event(
                "flash_command",
                args={"command": [], "cwd": str(self.config.source_dir)},
                result={"returncode": 0, "stdout_tail": result.stdout},
                ok=True,
            )
            return result
        return run_command(
            self.config.flash_command,
            self.config.source_dir,
            event="flash_command",
            timeout_s=self.config.command_timeout_s,
        )

    def smoke_test(self) -> SmokeTestResult:
        if not self.config.smoke_test_command:
            result = SmokeTestResult(
                ok=True,
                command=[],
                stdout="No smoke test command configured.",
                stderr="",
                returncode=0,
            )
            append_audit_event(
                "smoke_test_command",
                args={"command": [], "cwd": str(self.config.source_dir)},
                result={"returncode": 0, "stdout_tail": result.stdout},
                ok=True,
            )
            return result
        result = run_command(
            self.config.smoke_test_command,
            self.config.source_dir,
            event="smoke_test_command",
            timeout_s=self.config.command_timeout_s,
        )
        return SmokeTestResult(
            ok=result.ok,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    def collect_runtime_log(self) -> RuntimeLogResult:
        if not self.config.runtime_log_command:
            result = RuntimeLogResult(
                ok=True,
                command=[],
                stdout="No runtime log command configured.",
                stderr="",
                returncode=0,
                source="none",
                observations=[],
            )
            append_audit_event(
                "runtime_log_command",
                args={"command": [], "cwd": str(self.config.source_dir)},
                result={"returncode": 0, "stdout_tail": result.stdout, "observations": []},
                ok=True,
            )
            return result
        result = run_command(
            self.config.runtime_log_command,
            self.config.source_dir,
            event="runtime_log_command",
            timeout_s=self.config.runtime_log_timeout_s,
        )
        observations = extract_runtime_observations(result.stdout + "\n" + result.stderr)
        return RuntimeLogResult(
            ok=result.ok,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            source="command",
            observations=observations,
        )


def run_command(command: list[str], cwd, event: str, timeout_s: float | None = None) -> BuildResult:
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout_s)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result = BuildResult(
            ok=False,
            command=command,
            stdout=getattr(exc, "stdout", "") or "",
            stderr=str(exc),
            returncode=-1,
            errors=[str(exc)],
        )
        append_audit_event(
            event,
            args={"command": command, "cwd": str(cwd)},
            result={"returncode": result.returncode, "stderr_tail": result.stderr, "errors": result.errors},
            ok=False,
        )
        return result
    combined = completed.stdout + "\n" + completed.stderr
    result = BuildResult(
        ok=completed.returncode == 0,
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
        errors=extract_errors(combined),
        warnings=extract_warnings(combined),
    )
    append_audit_event(
        event,
        args={"command": command, "cwd": str(cwd)},
        result={
            "returncode": result.returncode,
            "stdout_tail": tail_text(result.stdout),
            "stderr_tail": tail_text(result.stderr),
            "errors": result.errors,
            "warnings": result.warnings,
        },
        ok=result.ok,
    )
    return result


def extract_errors(output: str) -> list[str]:
    patterns = [
        r"^.*error:.*$",
        r"^.*undefined reference.*$",
        r"^.*No such file or directory.*$",
        r"^.*fatal error:.*$",
        r"^.*failed:.*$",
    ]
    errors: list[str] = []
    for line in output.splitlines():
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns):
            errors.append(line.strip())
    return errors


def extract_runtime_observations(output: str) -> list[str]:
    observations: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        observations.append(stripped)
        if len(observations) >= 50:
            break
    return observations


def extract_warnings(output: str) -> list[str]:
    warnings: list[str] = []
    for line in output.splitlines():
        if re.search(r"warning[: ]", line, re.IGNORECASE):
            warnings.append(line.strip())
    return warnings


def _no_build_command(cwd) -> BuildResult:
    result = BuildResult(
        ok=True,
        command=[],
        stdout="No build command configured.",
        stderr="",
        returncode=0,
    )
    append_audit_event(
        "build_command",
        args={"command": [], "cwd": str(cwd)},
        result={"returncode": 0, "stdout_tail": result.stdout},
        ok=True,
    )
    return result
