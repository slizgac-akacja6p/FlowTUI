"""Analytics storage — thread-safe append-only log of invocations."""
from __future__ import annotations

import json
from datetime import datetime, date, timezone
from pathlib import Path
from filelock import FileLock


class AnalyticsStorage:
    """Thread-safe append-only log for analytics records."""

    def __init__(self, filepath: Path) -> None:
        """Initialize storage with a filepath."""
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = Path(str(self.filepath) + ".lock")

    def append(self, record: dict) -> None:
        """Append a record to the log (thread-safe via filelock).

        Automatically adds timestamp in ISO8601 format (UTC) if not present.
        """
        if "timestamp" not in record:
            record["timestamp"] = datetime.now(timezone.utc).isoformat()

        with FileLock(str(self.lock_path), timeout=10):
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    def read_today(self) -> list[dict]:
        """Read all records from today (by timestamp date)."""
        today = date.today().isoformat()
        records = []
        if not self.filepath.exists():
            return records

        with FileLock(str(self.lock_path), timeout=10):
            with open(self.filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        # Extract date from ISO timestamp
                        timestamp = record.get("timestamp", "")
                        record_date = timestamp.split("T")[0] if timestamp else ""
                        if record_date == today:
                            records.append(record)
                    except json.JSONDecodeError:
                        pass  # skip malformed lines
        return records

    def read_all(self) -> list[dict]:
        """Read all records from the log."""
        records = []
        if not self.filepath.exists():
            return records

        with FileLock(str(self.lock_path), timeout=10):
            with open(self.filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        records.append(record)
                    except json.JSONDecodeError:
                        pass
        return records
