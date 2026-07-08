from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class AccessKind(str, Enum):
    READ = "read"
    WRITE = "write"
    CONTROL = "control"


@dataclass(frozen=True)
class DebugCommandRecord:
    command: str
    args: dict[str, Any]
    result: Any
    ok: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class RegisterValue:
    name: str
    value: int


@dataclass(frozen=True)
class MemoryBlock:
    address: int
    data: bytes


@dataclass(frozen=True)
class Breakpoint:
    id: str
    location: str


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class RuntimeLogResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int
    source: str
    observations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SmokeTestResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class DebugTargetConfig:
    backend: str
    executable: str | None = None
    gdb_path: str = "arm-none-eabi-gdb"
    remote: str = "localhost:3333"
    cwd: Path = Path(".")
    log_path: Path = Path("debug_runs/debug_commands.jsonl")
    server_command: list[str] | None = None
    server_cwd: Path | None = None
    server_startup_delay_s: float = 1.0
    connect_retries: int = 3
    connect_retry_delay_s: float = 1.0
    recover_on_disconnect: bool = True
    command_retries: int = 2
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildConfig:
    backend: str
    build_dir: Path = Path("build")
    source_dir: Path = Path(".")
    configure_command: list[str] | None = None
    build_command: list[str] | None = None
    flash_command: list[str] | None = None
    smoke_test_command: list[str] | None = None
    runtime_log_command: list[str] | None = None
    repair_command: list[str] | None = None
    command_timeout_s: float | None = None
    runtime_log_timeout_s: float | None = 10.0
    repair_timeout_s: float = 600.0
    max_repair_iterations: int = 3
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DebugTask:
    name: str
    breakpoints: list[str] = field(default_factory=list)
    registers: list[str] = field(default_factory=list)
    memory_reads: list[tuple[int, int]] = field(default_factory=list)
    reset_before_run: bool = True
    launch_from_vector_table: int | None = None
    step_count: int = 0
    break_timeout_s: float = 10.0
    record_path: Path | None = None
