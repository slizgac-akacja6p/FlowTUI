"""Startup updater — check and apply tool updates."""
from __future__ import annotations

import subprocess
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta


class StartupUpdater:
    """Check and update tools on startup."""

    def __init__(self, data_dir: Path, skip_if_recent: int = 86400):
        """Initialize updater with data directory.

        Args:
            data_dir: Path to .flowtui/ directory
            skip_if_recent: Skip update if last check was within this many seconds (default: 24h)
        """
        self.data_dir = Path(data_dir)
        self.skip_if_recent = skip_if_recent

    def _read_last_update(self) -> datetime | None:
        """Read last update timestamp from .flowtui/last_update.json.

        Returns:
            datetime of last update, or None if file doesn't exist
        """
        last_update_file = self.data_dir / "last_update.json"

        if not last_update_file.exists():
            return None

        try:
            with open(last_update_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                timestamp_str = data.get("timestamp")
                if timestamp_str:
                    return datetime.fromisoformat(timestamp_str)
        except Exception:
            pass

        return None

    def _write_last_update(self) -> None:
        """Write current timestamp to .flowtui/last_update.json."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        last_update_file = self.data_dir / "last_update.json"

        data = {"timestamp": datetime.now().isoformat()}
        with open(last_update_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    async def auto_update_tools(self, tools: list[str]) -> None:
        """Check and update tools if needed.

        Skips update if last check was within skip_if_recent seconds.
        In M1, logs check without actual update of CC/codex.

        Args:
            tools: List of tool names to check (e.g. ["cc", "codex"])
        """
        last_update = self._read_last_update()
        now = datetime.now()

        # Skip if last update was recent
        if last_update:
            time_since_update = now - last_update
            if time_since_update.total_seconds() < self.skip_if_recent:
                return

        # Mark update check as done
        self._write_last_update()

        # In M1: only log check, don't actually update CC/codex
        # Real update would be: pip install --upgrade flowtui
        # For now, tools are logged as checked but update skipped in implementation
