"""Tests for invoker module — MockCLI and InvokeResult."""

import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest

from flowtui.core.invoker import (
    CLIInvoker,
    InvokeResult,
    MockCLI,
    SubprocessInvoker,
)


class TestInvokeResult:
    """Test InvokeResult dataclass."""

    def test_invoke_result_basic(self):
        """Create InvokeResult with basic fields."""
        result = InvokeResult(
            stdout="hello",
            stderr="",
            returncode=0,
            duration_sec=1.5,
        )
        assert result.stdout == "hello"
        assert result.returncode == 0
        assert result.timed_out is False

    def test_invoke_result_timed_out(self):
        """InvokeResult with timed_out flag."""
        result = InvokeResult(
            stdout="",
            stderr="Timeout",
            returncode=-1,
            duration_sec=300.0,
            timed_out=True,
        )
        assert result.timed_out is True
        assert result.returncode == -1

    def test_invoke_result_stderr(self):
        """InvokeResult captures stderr."""
        result = InvokeResult(
            stdout="output",
            stderr="error message",
            returncode=1,
            duration_sec=0.5,
        )
        assert result.stderr == "error message"
        assert result.returncode == 1


class TestMockCLI:
    """Test MockCLI — predefined responses."""

    @pytest.mark.asyncio
    async def test_mock_cli_returns_configured_response(self):
        """MockCLI with responses dict returns configured output."""
        mock = MockCLI(responses={"cc": "hello from cc"})
        result = await mock.invoke("cc", [], Path("."))

        assert result.stdout == "hello from cc"
        assert result.stderr == ""
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_mock_cli_unknown_tool(self):
        """MockCLI with unknown tool returns empty output (no raise)."""
        mock = MockCLI(responses={"cc": "hello"})
        result = await mock.invoke("unknown_tool", [], Path("."))

        assert result.stdout == ""
        assert result.returncode == 0
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_mock_cli_records_calls(self):
        """MockCLI records all invocations in calls list."""
        mock = MockCLI(responses={"cc": "output"})
        await mock.invoke("cc", ["--help"], Path("/tmp"))

        assert len(mock.calls) == 1
        call = mock.calls[0]
        assert call["tool"] == "cc"
        assert call["args"] == ["--help"]
        assert call["cwd"] == "/tmp"
        assert call["timeout"] == 300.0

    @pytest.mark.asyncio
    async def test_mock_cli_multiple_calls(self):
        """MockCLI records multiple calls."""
        mock = MockCLI(responses={"cc": "out", "codex": "other"})
        await mock.invoke("cc", [], Path("."))
        await mock.invoke("codex", [], Path("."))

        assert len(mock.calls) == 2
        assert mock.calls[0]["tool"] == "cc"
        assert mock.calls[1]["tool"] == "codex"

    @pytest.mark.asyncio
    async def test_mock_cli_with_delay(self):
        """MockCLI respects delay parameter."""
        import time

        mock = MockCLI(responses={"cc": "slow"}, delay=0.05)
        start = time.monotonic()
        result = await mock.invoke("cc", [], Path("."))
        elapsed = time.monotonic() - start

        assert result.stdout == "slow"
        assert elapsed >= 0.05

    @pytest.mark.asyncio
    async def test_mock_cli_streaming(self):
        """MockCLI streaming yields lines from response."""
        mock = MockCLI(responses={"cc": "line1\nline2\nline3"})
        lines = []
        async for line in mock.invoke_streaming("cc", [], Path(".")):
            lines.append(line)

        assert len(lines) == 3
        assert lines[0].strip() == "line1"
        assert lines[1].strip() == "line2"
        assert lines[2].strip() == "line3"

    @pytest.mark.asyncio
    async def test_mock_cli_streaming_records_calls(self):
        """MockCLI streaming also records calls."""
        mock = MockCLI(responses={"cc": "a\nb"})
        async for _ in mock.invoke_streaming("cc", ["arg"], Path("/home")):
            pass

        assert len(mock.calls) == 1
        assert mock.calls[0]["tool"] == "cc"
        assert mock.calls[0]["args"] == ["arg"]

    @pytest.mark.asyncio
    async def test_mock_cli_streaming_empty(self):
        """MockCLI streaming with empty response yields nothing."""
        mock = MockCLI(responses={"cc": ""})
        lines = []
        async for line in mock.invoke_streaming("cc", [], Path(".")):
            lines.append(line)

        assert lines == []

    @pytest.mark.asyncio
    async def test_mock_cli_streaming_unknown_tool(self):
        """MockCLI streaming with unknown tool yields nothing."""
        mock = MockCLI(responses={})
        lines = []
        async for line in mock.invoke_streaming("cc", [], Path(".")):
            lines.append(line)

        assert lines == []

    @pytest.mark.asyncio
    async def test_mock_cli_implements_protocol(self):
        """MockCLI implements CLIInvoker protocol."""
        mock = MockCLI()
        assert isinstance(mock, CLIInvoker)

    @pytest.mark.asyncio
    async def test_mock_cli_custom_timeout(self):
        """MockCLI accepts custom timeout parameter."""
        mock = MockCLI(responses={"cc": "data"})
        result = await mock.invoke("cc", [], Path("."), timeout=600.0)

        assert result.stdout == "data"
        assert mock.calls[0]["timeout"] == 600.0
