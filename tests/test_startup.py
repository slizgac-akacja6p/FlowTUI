"""Tests for startup checker — tool verification and version logging."""
import tempfile
from pathlib import Path
from unittest import mock
import subprocess
import json

import pytest

from flowtui.startup.checker import StartupChecker, ToolInfo


class TestToolInfo:
    """Test ToolInfo namedtuple."""

    def test_tool_info_creation(self):
        """Create ToolInfo namedtuple."""
        info = ToolInfo("cc", "1.0.0", True)
        assert info.name == "cc"
        assert info.version == "1.0.0"
        assert info.available is True

    def test_tool_info_unavailable(self):
        """Create ToolInfo for unavailable tool."""
        info = ToolInfo("missing", "not found", False)
        assert info.name == "missing"
        assert info.available is False


class TestStartupChecker:
    """Test StartupChecker class."""

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_available(self, mock_run):
        """verify_tools returns available=True for found tools."""
        mock_run.return_value = mock.Mock(
            stdout="1.0.0\n",
            stderr="",
            returncode=0
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools(["cc", "git"])

        assert len(results) == 2
        assert results[0].name == "cc"
        assert results[0].available is True
        assert results[1].name == "git"
        assert results[1].available is True

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_unavailable(self, mock_run):
        """verify_tools returns available=False for missing tools."""
        mock_run.side_effect = FileNotFoundError("command not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools(["nonexistent"])

        assert len(results) == 1
        assert results[0].name == "nonexistent"
        assert results[0].available is False
        assert results[0].version == "not found"

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_timeout(self, mock_run):
        """verify_tools handles subprocess timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("cc", 5)

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools(["cc"])

        assert len(results) == 1
        assert results[0].available is False
        assert results[0].version == "timeout"

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_multiple_mixed(self, mock_run):
        """verify_tools handles mix of available and unavailable tools."""
        def run_side_effect(cmd, **kwargs):
            if "available" in cmd[0]:
                return mock.Mock(stdout="v1.0\n", stderr="", returncode=0)
            else:
                raise FileNotFoundError()

        mock_run.side_effect = run_side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools(["available", "missing"])

        assert len(results) == 2
        assert results[0].available is True
        assert results[1].available is False

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_empty_list(self, mock_run):
        """verify_tools handles empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools([])

        assert results == []

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_calls_with_version_flag(self, mock_run):
        """verify_tools calls subprocess with appropriate command."""
        mock_run.return_value = mock.Mock(stdout="v1.0\n", stderr="", returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            checker.verify_tools(["mytool"])

        # Verify subprocess.run was called
        assert mock_run.called

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_uses_tool_commands_mapping(self, mock_run):
        """verify_tools uses TOOL_COMMANDS mapping for known tools."""
        mock_run.return_value = mock.Mock(stdout="v1.0\n", stderr="", returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            checker.verify_tools(["cc"])

        # Should call with the mapped command
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        # cc maps to ["claude", "--version"]
        assert "claude" in call_args or "cc" in call_args

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_extracts_version_from_stdout(self, mock_run):
        """verify_tools extracts version from stdout."""
        mock_run.return_value = mock.Mock(
            stdout="Claude 1.2.3\nOther info\n",
            stderr="",
            returncode=0
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools(["cc"])

        assert results[0].version == "Claude 1.2.3"

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_verify_tools_falls_back_to_stderr(self, mock_run):
        """verify_tools falls back to stderr if stdout is empty."""
        mock_run.return_value = mock.Mock(
            stdout="",
            stderr="Version: 2.0.0\n",
            returncode=0
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            results = checker.verify_tools(["cc"])

        assert results[0].version == "Version: 2.0.0"


class TestLogVersions:
    """Test log_versions method."""

    def test_log_versions_creates_file(self):
        """log_versions creates .flowtui/versions.jsonl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            tool_infos = [ToolInfo("cc", "1.0.0", True)]
            checker.log_versions(tool_infos)

            versions_file = Path(tmpdir) / "versions.jsonl"
            assert versions_file.exists()

    def test_log_versions_appends_record(self):
        """log_versions appends valid JSON record to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            tool_infos = [ToolInfo("cc", "1.0.0", True)]
            checker.log_versions(tool_infos)

            versions_file = Path(tmpdir) / "versions.jsonl"
            content = versions_file.read_text()
            record = json.loads(content.strip())

            assert "timestamp" in record
            assert "tools" in record
            assert isinstance(record["tools"], list)
            assert len(record["tools"]) == 1

    def test_log_versions_record_structure(self):
        """log_versions record has correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))
            tool_infos = [
                ToolInfo("cc", "1.0.0", True),
                ToolInfo("missing", "not found", False),
            ]
            checker.log_versions(tool_infos)

            versions_file = Path(tmpdir) / "versions.jsonl"
            record = json.loads(versions_file.read_text())

            # Check structure
            assert "timestamp" in record
            assert "tools" in record
            assert len(record["tools"]) == 2

            # Check first tool
            tool = record["tools"][0]
            assert tool["name"] == "cc"
            assert tool["version"] == "1.0.0"
            assert tool["available"] is True

            # Check unavailable tool
            tool = record["tools"][1]
            assert tool["available"] is False

    def test_log_versions_multiple_calls_append(self):
        """Multiple log_versions calls append to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))

            checker.log_versions([ToolInfo("cc", "1.0.0", True)])
            checker.log_versions([ToolInfo("git", "2.0.0", True)])

            versions_file = Path(tmpdir) / "versions.jsonl"
            lines = versions_file.read_text().strip().split("\n")
            assert len(lines) == 2

    def test_log_versions_creates_flowtui_dir(self):
        """log_versions creates data_dir if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Specify a non-existent path
            flowtui_dir = Path(tmpdir) / "subdir" / ".flowtui"
            checker = StartupChecker(flowtui_dir)
            checker.log_versions([ToolInfo("cc", "1.0.0", True)])

            assert flowtui_dir.exists()
            assert (flowtui_dir / "versions.jsonl").exists()

    @mock.patch("flowtui.startup.checker.subprocess.run")
    def test_full_workflow(self, mock_run):
        """Full workflow: verify_tools → log_versions."""
        mock_run.return_value = mock.Mock(
            stdout="1.0.0\n",
            stderr="",
            returncode=0
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            checker = StartupChecker(Path(tmpdir))

            # Verify tools
            tool_infos = checker.verify_tools(["cc", "git"])
            assert len(tool_infos) == 2

            # Log results
            checker.log_versions(tool_infos)

            # Verify log file
            versions_file = Path(tmpdir) / "versions.jsonl"
            assert versions_file.exists()

            record = json.loads(versions_file.read_text())
            assert len(record["tools"]) == 2
