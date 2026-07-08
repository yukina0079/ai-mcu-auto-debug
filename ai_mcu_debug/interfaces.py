from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Breakpoint, BuildResult, MemoryBlock, RegisterValue, RepairResult, RuntimeLogResult, SmokeTestResult


class DebugAdapter(ABC):
    """Backend-neutral MCU debug control interface."""

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    def diagnostics(self) -> dict[str, object]:
        return {}

    @abstractmethod
    def halt(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def resume(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def wait_for_stop(self, timeout_s: float = 10.0) -> str:
        raise NotImplementedError

    @abstractmethod
    def step(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset(self, halt: bool = True) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_breakpoint(self, location: str) -> Breakpoint:
        raise NotImplementedError

    @abstractmethod
    def delete_breakpoint(self, breakpoint_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_register(self, name: str) -> RegisterValue:
        raise NotImplementedError

    @abstractmethod
    def write_register(self, name: str, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_memory(self, address: int, length: int) -> MemoryBlock:
        raise NotImplementedError

    @abstractmethod
    def write_memory(self, address: int, data: bytes) -> None:
        raise NotImplementedError


class BuildAdapter(ABC):
    """Backend-neutral build/flash interface."""

    @abstractmethod
    def build(self) -> BuildResult:
        raise NotImplementedError

    @abstractmethod
    def flash(self) -> BuildResult:
        raise NotImplementedError

    @abstractmethod
    def smoke_test(self) -> SmokeTestResult:
        raise NotImplementedError

    def collect_runtime_log(self) -> RuntimeLogResult:
        return RuntimeLogResult(
            ok=True,
            command=[],
            stdout="No runtime log command configured.",
            stderr="",
            returncode=0,
            source="none",
            observations=[],
        )


class RepairAdapter(ABC):
    """Thin wrapper around an existing AI coding tool such as Codex, Claude Code, or Aider."""

    @abstractmethod
    def repair_build(self, result: BuildResult, attempt: int) -> RepairResult:
        raise NotImplementedError


class KnowledgeAdapter(ABC):
    """Backend-neutral MCU knowledge lookup and guard interface."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def vector_search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def explain_register(self, identifier: str) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def validate_register_write(self, identifier: str, value: int) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def validate_address_write(self, address: int, length: int) -> dict[str, object]:
        raise NotImplementedError
