from __future__ import annotations

import re
import subprocess
import threading
import time
from collections import deque
from queue import Queue
from typing import Any

from ai_mcu_debug.command_log import JsonlCommandLogger
from ai_mcu_debug.interfaces import DebugAdapter
from ai_mcu_debug.models import Breakpoint, DebugTargetConfig, MemoryBlock, RegisterValue


class GdbRemoteAdapter(DebugAdapter):
    """GDB/MI adapter that can sit behind OpenOCD, J-Link GDB Server, or pyOCD GDB server."""

    def __init__(self, config: DebugTargetConfig) -> None:
        self.config = config
        self.logger = JsonlCommandLogger(config.log_path)
        self.process: subprocess.Popen[str] | None = None
        self.server_process: subprocess.Popen[str] | None = None
        self._server_output_tail: deque[str] = deque(maxlen=200)
        self._server_output_thread: threading.Thread | None = None
        self._token = 0
        self._lock = threading.Lock()
        self._known_breakpoint_locations: list[str] = []
        self._gdb_stdout_timed_out = False

    def connect(self) -> None:
        self._start_server_if_configured()
        last_error: Exception | None = None
        attempts = max(1, self.config.connect_retries)
        for attempt in range(1, attempts + 1):
            try:
                self._start_gdb()
                self._mi(
                    f"-target-select extended-remote {self.config.remote}",
                    "connect",
                    {"remote": self.config.remote, "attempt": attempt},
                    allow_recovery=False,
                )
                return
            except Exception as exc:
                last_error = exc
                self._stop_gdb(graceful=False)
                if attempt < attempts:
                    time.sleep(self.config.connect_retry_delay_s)
        diagnostics = self.diagnostics()
        raise RuntimeError(
            f"Could not connect to GDB remote target after {attempts} attempt(s). "
            f"Diagnostics: {diagnostics}"
        ) from last_error

    def _start_server_if_configured(self) -> None:
        if not self.config.server_command:
            return
        if self.server_process and self.server_process.poll() is None:
            return
        self.server_process = None
        self.server_process = subprocess.Popen(
            self.config.server_command,
            cwd=self.config.server_cwd or self.config.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        self._start_server_output_reader()
        time.sleep(self.config.server_startup_delay_s)

    def _start_gdb(self) -> None:
        command = [self.config.gdb_path, "--interpreter=mi2", "--quiet"]
        if self.config.executable:
            command.append(self.config.executable)
        self.process = subprocess.Popen(
            command,
            cwd=self.config.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        self._gdb_stdout_timed_out = False
        self._drain_until_prompt()

    def close(self) -> None:
        # A resumed target may never produce a prompt for -gdb-exit. Process
        # termination is bounded and still detaches cleanly from the target.
        self._stop_gdb(graceful=False)
        if self.server_process:
            self._terminate_process(self.server_process)
            self.server_process = None
        if self._server_output_thread:
            self._server_output_thread.join(timeout=1)
            self._server_output_thread = None

    def _stop_gdb(self, graceful: bool) -> None:
        if not self.process:
            return
        try:
            if graceful and not self._gdb_stdout_timed_out:
                self._mi("-gdb-exit", "close", {}, allow_recovery=False)
        except Exception:
            pass
        finally:
            if self.process:
                self._terminate_process(self.process)
            self.process = None

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def diagnostics(self) -> dict[str, object]:
        return {
            "remote": self.config.remote,
            "gdb_path": self.config.gdb_path,
            "executable": self.config.executable,
            "server_command": self.config.server_command,
            "gdb_running": self.process is not None and self.process.poll() is None,
            "server_running": self.server_process is not None and self.server_process.poll() is None,
            "server_returncode": self.server_process.poll() if self.server_process else None,
            "server_output_tail": list(self._server_output_tail),
            "extra": self.config.extra,
        }

    def halt(self) -> None:
        self._mi("-exec-interrupt", "halt", {})

    def resume(self) -> None:
        self._mi("-exec-continue", "resume", {})

    def wait_for_stop(self, timeout_s: float = 10.0) -> str:
        deadline = time.monotonic() + timeout_s
        lines: list[str] = []
        ok = False
        try:
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                current = self._readline_with_timeout(remaining)
                if current is None:
                    break
                lines.append(current)
                if current.startswith("*stopped") or '"stopped"' in current:
                    ok = True
                    return "".join(lines)
            raise TimeoutError(f"Target did not stop within {timeout_s} seconds")
        finally:
            self.logger.record("wait_for_stop", {"timeout_s": timeout_s}, "".join(lines), ok)

    def step(self) -> None:
        self._mi("-exec-step-instruction", "step", {})

    def reset(self, halt: bool = True) -> None:
        monitor_command = "monitor reset halt" if halt else "monitor reset"
        self._console(monitor_command, "reset", {"halt": halt})

    def set_breakpoint(self, location: str) -> Breakpoint:
        output = self._mi(f"-break-insert {location}", "set_breakpoint", {"location": location})
        match = re.search(r'number="([^"]+)"', output)
        breakpoint_id = match.group(1) if match else location
        if location not in self._known_breakpoint_locations:
            self._known_breakpoint_locations.append(location)
        return Breakpoint(id=breakpoint_id, location=location)

    def delete_breakpoint(self, breakpoint_id: str) -> None:
        self._mi(f"-break-delete {breakpoint_id}", "delete_breakpoint", {"breakpoint_id": breakpoint_id})

    def read_register(self, name: str) -> RegisterValue:
        output = self._console(f"p/x ${name}", "read_register", {"name": name})
        value = _parse_hex_value(output)
        return RegisterValue(name=name, value=value)

    def write_register(self, name: str, value: int) -> None:
        self._console(f"set ${name}=0x{value:x}", "write_register", {"name": name, "value": value})

    def read_memory(self, address: int, length: int) -> MemoryBlock:
        output = self._mi(
            f"-data-read-memory-bytes 0x{address:x} {length}",
            "read_memory",
            {"address": address, "length": length},
        )
        data = _parse_memory_bytes(output)
        return MemoryBlock(address=address, data=data)

    def write_memory(self, address: int, data: bytes) -> None:
        hex_data = "".join(f"{byte:02x}" for byte in data)
        self._mi(
            f"-data-write-memory-bytes 0x{address:x} {hex_data}",
            "write_memory",
            {"address": address, "length": len(data)},
        )

    def _console(self, command: str, log_command: str, args: dict[str, Any]) -> str:
        return self._mi(f'-interpreter-exec console "{command}"', log_command, args)

    def _mi(self, command: str, log_command: str, args: dict[str, Any], allow_recovery: bool = True) -> str:
        with self._lock:
            attempts = max(1, self.config.command_retries if allow_recovery and self.config.recover_on_disconnect else 1)
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return self._mi_once(command, log_command, {**args, "command_attempt": attempt})
                except Exception as exc:
                    last_error = exc
                    if attempt >= attempts:
                        break
                    self._recover_connection()
            raise RuntimeError(f"GDB command failed after {attempts} attempt(s): {log_command}") from last_error

    def _mi_once(self, command: str, log_command: str, args: dict[str, Any]) -> str:
        self._token += 1
        token = self._token
        line = f"{token}{command}"
        ok = False
        try:
            output = self._send_and_collect(line, token)
            ok = (
                f"{token}^done" in output
                or f"{token}^running" in output
                or f"{token}^connected" in output
                or f"{token}^exit" in output
            )
            if not ok:
                raise RuntimeError(output)
            return output
        finally:
            self.logger.record(log_command, args, locals().get("output", ""), ok)

    def _recover_connection(self) -> None:
        self.logger.record("recover_connection", {"remote": self.config.remote}, "restart_gdb", False)
        self._stop_gdb(graceful=False)
        self._start_server_if_configured()
        last_error: Exception | None = None
        attempts = max(1, self.config.connect_retries)
        for attempt in range(1, attempts + 1):
            try:
                self._start_gdb()
                self._mi_once(
                    f"-target-select extended-remote {self.config.remote}",
                    "reconnect",
                    {"remote": self.config.remote, "attempt": attempt},
                )
                for location in self._known_breakpoint_locations:
                    self._mi_once(
                        f"-break-insert {location}",
                        "restore_breakpoint",
                        {"location": location},
                    )
                return
            except Exception as exc:
                last_error = exc
                self._stop_gdb(graceful=False)
                if attempt < attempts:
                    time.sleep(self.config.connect_retry_delay_s)
        raise RuntimeError("Could not recover GDB remote session") from last_error

    def _send_and_collect(self, line: str, token: int) -> str:
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("GDB process is not connected")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        lines: list[str] = []
        while True:
            current = self.process.stdout.readline()
            if current == "":
                raise RuntimeError("GDB exited unexpectedly")
            lines.append(current)
            if current.startswith(f"{token}^"):
                break
        return "".join(lines)

    def _readline_with_timeout(self, timeout_s: float) -> str | None:
        if not self.process or not self.process.stdout:
            raise RuntimeError("GDB process is not connected")
        queue: Queue[str] = Queue(maxsize=1)

        def read_line() -> None:
            queue.put(self.process.stdout.readline())

        thread = threading.Thread(target=read_line, daemon=True)
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            self._gdb_stdout_timed_out = True
            return None
        current = queue.get()
        if current == "":
            raise RuntimeError("GDB exited unexpectedly")
        return current

    def _start_server_output_reader(self) -> None:
        if not self.server_process or not self.server_process.stdout:
            return

        def read_output() -> None:
            assert self.server_process is not None
            assert self.server_process.stdout is not None
            for line in self.server_process.stdout:
                self._server_output_tail.append(line.rstrip())

        self._server_output_thread = threading.Thread(target=read_output, daemon=True)
        self._server_output_thread.start()

    def _drain_until_prompt(self) -> None:
        if not self.process or not self.process.stdout:
            return
        while True:
            line = self.process.stdout.readline()
            if line == "" or line.strip() == "(gdb)":
                break


def _parse_hex_value(output: str) -> int:
    matches = re.findall(r"0x[0-9a-fA-F]+", output)
    if not matches:
        raise ValueError(f"No hex value found in GDB output: {output}")
    return int(matches[-1], 16)


def _parse_memory_bytes(output: str) -> bytes:
    match = re.search(r'contents="([0-9a-fA-F]*)"', output)
    if not match:
        return bytes()
    return bytes.fromhex(match.group(1))
