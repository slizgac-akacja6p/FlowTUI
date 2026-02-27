"""Startup checker — verify tool availability and log versions."""
from __future__ import annotations

import subprocess
import json
from pathlib import Path
from datetime import datetime
from collections import namedtuple

# Tool information: (name, version, available)
ToolInfo = namedtuple("ToolInfo", ["name", "version", "available"])


class StartupChecker:
    """Verify tool availability and version history."""

    # Maps tool names to command for version check
    TOOL_COMMANDS = {
        "cc": ["claude", "--version"],
        "codex": ["codex", "--version"],
        "gemini": ["gemini", "--version"],
    }

    def __init__(self, data_dir: Path):
        """Initialize checker with data directory.

        Args:
            data_dir: Path to .flowtui/ directory
        """
        self.data_dir = Path(data_dir)

    def verify_tools(self, tools: list[str]) -> list[ToolInfo]:
        """Verify that tools are available and extract versions.

        Args:
            tools: List of tool names (e.g. ["cc", "codex"])

        Returns:
            List of ToolInfo namedtuples with availability and version
        """
        results = []

        for tool in tools:
            # Get command to run (default: tool --version)
            cmd = self.TOOL_COMMANDS.get(tool, [tool, "--version"])

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=5,
                    check=False,
                    text=True,
                )
                # Extract version from stdout or stderr
                output = result.stdout.strip() or result.stderr.strip()
                version_str = output.split("\n")[0] if output else "unknown"
                results.append(ToolInfo(tool, version_str, True))

            except FileNotFoundError:
                results.append(ToolInfo(tool, "not found", False))

            except subprocess.TimeoutExpired:
                results.append(ToolInfo(tool, "timeout", False))

            except Exception as e:
                results.append(ToolInfo(tool, str(e), False))

        return results

    def log_versions(self, tool_infos: list[ToolInfo]) -> None:
        """Log tool versions to .flowtui/versions.jsonl.

        Args:
            tool_infos: List of ToolInfo from verify_tools()
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        versions_file = self.data_dir / "versions.jsonl"

        record = {
            "timestamp": datetime.now().isoformat(),
            "tools": [
                {
                    "name": info.name,
                    "version": info.version,
                    "available": info.available,
                }
                for info in tool_infos
            ],
        }

        with open(versions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
