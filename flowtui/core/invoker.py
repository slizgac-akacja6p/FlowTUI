"""CLI invoker for subprocess execution (CC, Codex, Gemini)."""

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass
class InvokeResult:
    """Result of a CLI invocation."""
    stdout: str
    stderr: str
    returncode: int
    duration_sec: float
    timed_out: bool = False


@runtime_checkable
class CLIInvoker(Protocol):
    """Duck-typed interface for CLI tools (CC, Codex, Gemini)."""

    async def invoke(
        self,
        tool: str,
        args: list[str],
        cwd: Path,
        timeout: float = 300.0,
    ) -> InvokeResult:
        """Execute CLI tool and return result."""
        ...

    async def invoke_streaming(
        self,
        tool: str,
        args: list[str],
        cwd: Path,
        timeout: float = 300.0,
    ) -> AsyncIterator[str]:
        """Execute CLI tool and stream stdout line by line."""
        ...


class SubprocessInvoker:
    """Real CLI invoker using asyncio subprocess."""

    TOOL_COMMANDS: dict[str, list[str]] = {
        "cc": ["claude"],
        "codex": ["codex"],
        "gemini": ["gemini"],
    }

    HEARTBEAT_TIMEOUT = 60.0  # seconds of silence before kill

    async def invoke(
        self,
        tool: str,
        args: list[str],
        cwd: Path,
        timeout: float = 300.0,
    ) -> InvokeResult:
        """Execute CLI tool synchronously and return result."""
        if tool not in self.TOOL_COMMANDS:
            raise ValueError(f"Unknown tool: {tool}")

        cmd = self.TOOL_COMMANDS[tool] + args
        start_time = time.monotonic()

        try:
            # Strip CLAUDECODE to allow nested CC invocations from FlowTUI
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                duration = time.monotonic() - start_time
                return InvokeResult(
                    stdout="",
                    stderr="Process killed due to timeout",
                    returncode=-1,
                    duration_sec=duration,
                    timed_out=True,
                )

            duration = time.monotonic() - start_time
            return InvokeResult(
                stdout=stdout_data.decode("utf-8", errors="replace"),
                stderr=stderr_data.decode("utf-8", errors="replace"),
                returncode=proc.returncode or 0,
                duration_sec=duration,
                timed_out=False,
            )
        except FileNotFoundError:
            duration = time.monotonic() - start_time
            raise RuntimeError(f"Tool not found: {tool} (command: {cmd[0]})") from None

    async def invoke_streaming(
        self,
        tool: str,
        args: list[str],
        cwd: Path,
        timeout: float = 300.0,
    ) -> AsyncIterator[str]:
        """Execute CLI tool and stream stdout line by line."""
        if tool not in self.TOOL_COMMANDS:
            raise ValueError(f"Unknown tool: {tool}")

        cmd = self.TOOL_COMMANDS[tool] + args
        start_time = time.monotonic()

        try:
            # Strip CLAUDECODE to allow nested CC invocations from FlowTUI
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except FileNotFoundError:
            raise RuntimeError(f"Tool not found: {tool} (command: {cmd[0]})") from None

        _streaming_done = False
        try:
            while True:
                # Heartbeat: wait for next line with timeout
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=self.HEARTBEAT_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                    raise TimeoutError(
                        f"No output for {self.HEARTBEAT_TIMEOUT}s (heartbeat timeout)"
                    )

                if not line:
                    # EOF
                    break

                # Check global timeout
                elapsed = time.monotonic() - start_time
                if elapsed > timeout:
                    proc.kill()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                    raise TimeoutError(f"Global timeout exceeded: {elapsed:.1f}s > {timeout}s")

                yield line.decode("utf-8", errors="replace")

            _streaming_done = True
            # Wait for process to finish
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            # Timeout during streaming vs cleanup depends on _streaming_done flag
            if not _streaming_done:
                # Timeout during readline (shouldn't happen here, but guard)
                proc.kill()
                raise TimeoutError("Streaming timed out during output collection")
            else:
                # Timeout waiting for proc cleanup after EOF — just kill it
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass


class MockCLI:
    """Mock invoker for tests — returns predefined responses."""

    def __init__(self, responses: dict[str, str] | None = None, delay: float = 0.0):
        """Initialize mock CLI.

        Args:
            responses: dict mapping tool names to mock output
            delay: artificial delay per invoke (seconds)
        """
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.delay = delay

    async def invoke(
        self,
        tool: str,
        args: list[str],
        cwd: Path,
        timeout: float = 300.0,
    ) -> InvokeResult:
        """Execute mock CLI and return result."""
        self.calls.append(
            {"tool": tool, "args": args, "cwd": str(cwd), "timeout": timeout}
        )

        start_time = time.monotonic()

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        duration = time.monotonic() - start_time
        output = self.responses.get(tool, "")

        return InvokeResult(
            stdout=output,
            stderr="",
            returncode=0,
            duration_sec=duration,
            timed_out=False,
        )

    async def invoke_streaming(
        self,
        tool: str,
        args: list[str],
        cwd: Path,
        timeout: float = 300.0,
    ) -> AsyncIterator[str]:
        """Execute mock CLI and stream output line by line."""
        self.calls.append(
            {"tool": tool, "args": args, "cwd": str(cwd), "timeout": timeout}
        )

        output = self.responses.get(tool, "")
        lines = output.split("\n") if output else []

        for line in lines:
            if not line:  # skip empty lines
                continue
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            yield line + "\n"
