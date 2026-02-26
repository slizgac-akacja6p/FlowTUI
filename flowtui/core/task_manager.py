"""Task management — CRUD operations on TASK-XXX.md files."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


VALID_STATUSES = {"DRAFT", "TODO", "IN_PROGRESS", "IN_REVIEW", "DONE", "BLOCKED"}
VALID_PRIORITIES = {"high", "medium", "low"}


@dataclass
class Task:
    """Represents a single task from a TASK-XXX.md file."""

    id: str  # e.g. "TASK-001"
    title: str
    sprint: str = ""
    priority: str = "medium"
    assigned: str = "claude"
    status: str = "TODO"
    created: str = ""
    updated: str = ""
    context: str = ""
    requirements: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    log_entries: list[str] = field(default_factory=list)
    filepath: Path = field(default=Path("."), repr=False)

    @property
    def is_done(self) -> bool:
        """Check if task is in DONE status."""
        return self.status == "DONE"

    @property
    def is_blocked(self) -> bool:
        """Check if task is in BLOCKED status."""
        return self.status == "BLOCKED"


class TaskParseError(ValueError):
    """Raised when a TASK-XXX.md file cannot be parsed."""

    pass


class TaskNotFoundError(KeyError):
    """Raised when a task ID is not found."""

    pass


class TaskManager:
    """CRUD operations on TASK-XXX.md files in a tasks directory."""

    def __init__(self, tasks_dir: Path) -> None:
        """Initialize TaskManager with a tasks directory path."""
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    # ── Load ────────────────────────────────────────────────────────────────

    def load_all(self) -> list[Task]:
        """Load all TASK-XXX.md files, sorted by task ID."""
        import warnings

        tasks = []
        for path in sorted(self.tasks_dir.glob("TASK-*.md")):
            try:
                tasks.append(self._parse(path))
            except TaskParseError:
                warnings.warn(
                    f"Skipping malformed task file: {path}",
                    stacklevel=2,
                )
        return tasks

    def load(self, task_id: str) -> Task:
        """Load a single task by ID. Raises TaskNotFoundError if not found."""
        path = self.tasks_dir / f"{task_id}.md"
        if not path.exists():
            raise TaskNotFoundError(f"Task {task_id} not found at {path}")
        return self._parse(path)

    # ── Write ────────────────────────────────────────────────────────────────

    def create(self, task: Task) -> None:
        """Write a new TASK-XXX.md file."""
        filepath = self.tasks_dir / f"{task.id}.md"
        # Compute created/updated dates locally without mutating task parameter.
        created = task.created or date.today().isoformat()
        updated = date.today().isoformat()
        # Serialize with local values, task object is not modified.
        serialized = self._serialize_with_dates(task, created, updated)
        filepath.write_text(serialized, encoding="utf-8")

    def update_status(self, task_id: str, status: str, note: str = "") -> None:
        """Update task status and append to log."""
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status: {status}. Must be one of {VALID_STATUSES}"
            )
        task = self.load(task_id)
        task.status = status
        task.updated = date.today().isoformat()
        if note:
            task.log_entries.append(
                f"- {date.today().isoformat()}: [{status}] {note}"
            )
        else:
            task.log_entries.append(f"- {date.today().isoformat()}: Status → {status}")
        task.filepath.write_text(self._serialize(task), encoding="utf-8")

    def delete(self, task_id: str) -> None:
        """Delete a task file."""
        path = self.tasks_dir / f"{task_id}.md"
        if not path.exists():
            raise TaskNotFoundError(f"Task {task_id} not found")
        path.unlink()

    # ── Query ────────────────────────────────────────────────────────────────

    def by_status(self, status: str) -> list[Task]:
        """Return all tasks with given status."""
        return [t for t in self.load_all() if t.status == status]

    def next_todo(self) -> Task | None:
        """Return highest-priority TODO task, or None."""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        todos = self.by_status("TODO")
        if not todos:
            return None
        return min(todos, key=lambda t: priority_order.get(t.priority, 1))

    # ── Parse / Serialize ────────────────────────────────────────────────────

    def _parse(self, path: Path) -> Task:
        """Parse a TASK-XXX.md file into a Task object."""
        text = path.read_text(encoding="utf-8")

        # Extract task ID and title from first heading
        title_match = re.match(r"^# (TASK-\d+): (.+)$", text, re.MULTILINE)
        if not title_match:
            raise TaskParseError(f"Cannot parse task ID/title from {path}")

        task_id = title_match.group(1)
        title = title_match.group(2).strip()

        # Helper to extract single metadata value
        def _meta(key: str) -> str:
            m = re.search(
                rf"^- {key}: (.+)$", text, re.MULTILINE | re.IGNORECASE
            )
            return m.group(1).strip() if m else ""

        # Helper to extract section content (between ## Heading and next ## or EOF)
        def _section(heading: str) -> str:
            pattern = rf"^## {heading}\s*\n(.*?)(?=^## |\Z)"
            m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            return m.group(1).strip() if m else ""

        # Helper to extract list items from a section
        def _list_section(heading: str) -> list[str]:
            content = _section(heading)
            items = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    # Remove leading "- " if present, otherwise keep as-is
                    if stripped.startswith("- "):
                        items.append(stripped[2:])
                    else:
                        items.append(stripped)
            return items

        return Task(
            id=task_id,
            title=title,
            sprint=_meta("Sprint"),
            priority=_meta("Priority") or "medium",
            assigned=_meta("Assigned") or "claude",
            status=_meta("Status") or "TODO",
            created=_meta("Created"),
            updated=_meta("Updated"),
            context=_section("Kontekst"),
            requirements=_list_section("Wymagania"),
            files_to_modify=_list_section("Pliki do modyfikacji"),
            constraints=_list_section("Ograniczenia"),
            acceptance_criteria=_list_section("Kryteria akceptacji"),
            log_entries=_list_section("Log"),
            filepath=path,
        )

    def _serialize(self, task: Task) -> str:
        """Serialize a Task back to TASK-XXX.md format."""

        def _list(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) if items else ""

        return f"""# {task.id}: {task.title}

## Meta
- Sprint: {task.sprint}
- Priority: {task.priority}
- Assigned: {task.assigned}
- Status: {task.status}
- Created: {task.created}
- Updated: {task.updated}

## Kontekst
{task.context}

## Wymagania
{_list(task.requirements)}

## Pliki do modyfikacji
{_list(task.files_to_modify)}

## Ograniczenia
{_list(task.constraints)}

## Kryteria akceptacji
{_list(task.acceptance_criteria)}

## Log
{_list(task.log_entries)}
"""

    def _serialize_with_dates(self, task: Task, created: str, updated: str) -> str:
        """Serialize a Task with explicit created/updated dates (no mutation)."""

        def _list(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) if items else ""

        return f"""# {task.id}: {task.title}

## Meta
- Sprint: {task.sprint}
- Priority: {task.priority}
- Assigned: {task.assigned}
- Status: {task.status}
- Created: {created}
- Updated: {updated}

## Kontekst
{task.context}

## Wymagania
{_list(task.requirements)}

## Pliki do modyfikacji
{_list(task.files_to_modify)}

## Ograniczenia
{_list(task.constraints)}

## Kryteria akceptacji
{_list(task.acceptance_criteria)}

## Log
{_list(task.log_entries)}
"""
