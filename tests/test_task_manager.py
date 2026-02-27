"""Tests for TaskManager — CRUD operations on TASK-XXX.md files."""
import re
import tempfile
from pathlib import Path
from datetime import date

import pytest

from flowtui.core.task_manager import (
    Task,
    TaskManager,
    TaskParseError,
    TaskNotFoundError,
    VALID_STATUSES,
    VALID_PRIORITIES,
)


@pytest.fixture
def temp_tasks_dir():
    """Temporary directory for task files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_manager(temp_tasks_dir):
    """TaskManager instance with temp directory."""
    return TaskManager(temp_tasks_dir)


class TestTaskDataclass:
    """Test Task dataclass properties."""

    def test_task_is_done(self):
        task = Task(id="TASK-001", title="Test", status="DONE")
        assert task.is_done

    def test_task_is_not_done(self):
        task = Task(id="TASK-001", title="Test", status="TODO")
        assert not task.is_done

    def test_task_is_blocked(self):
        task = Task(id="TASK-001", title="Test", status="BLOCKED")
        assert task.is_blocked

    def test_task_is_not_blocked(self):
        task = Task(id="TASK-001", title="Test", status="TODO")
        assert not task.is_blocked


class TestTaskManagerCreate:
    """Test task creation."""

    def test_create_minimal_task(self, task_manager, temp_tasks_dir):
        """Create a task with minimal fields."""
        task = Task(id="TASK-001", title="Test Task")
        task_manager.create(task)

        path = temp_tasks_dir / "TASK-001.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "# TASK-001: Test Task" in content
        assert f"- Created: {date.today().isoformat()}" in content

    def test_create_full_task(self, task_manager, temp_tasks_dir):
        """Create a task with all fields."""
        task = Task(
            id="TASK-002",
            title="Full Task",
            sprint="sprint-001",
            priority="high",
            assigned="alice",
            status="IN_PROGRESS",
            created="2026-02-26",
            updated="2026-02-26",
            context="This is context",
            requirements=["req1", "req2"],
            files_to_modify=["src/file.py", "tests/test.py"],
            constraints=["no breaking changes"],
            acceptance_criteria=["[ ] test passes", "[ ] code review"],
            log_entries=["- 2026-02-26: Created"],
        )
        task_manager.create(task)

        path = temp_tasks_dir / "TASK-002.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "- Priority: high" in content
        assert "- Assigned: alice" in content
        assert "- Status: IN_PROGRESS" in content
        assert "This is context" in content
        assert "- req1" in content
        assert "- src/file.py" in content


class TestTaskManagerLoad:
    """Test task loading."""

    def test_load_nonexistent_task(self, task_manager):
        """Loading nonexistent task raises TaskNotFoundError."""
        with pytest.raises(TaskNotFoundError):
            task_manager.load("TASK-999")

    def test_load_single_task(self, task_manager, temp_tasks_dir):
        """Load a single task by ID."""
        original = Task(
            id="TASK-001",
            title="Load Test",
            sprint="sprint-001",
            priority="medium",
            assigned="bob",
            status="TODO",
        )
        task_manager.create(original)

        loaded = task_manager.load("TASK-001")
        assert loaded.id == "TASK-001"
        assert loaded.title == "Load Test"
        assert loaded.sprint == "sprint-001"
        assert loaded.priority == "medium"
        assert loaded.assigned == "bob"
        assert loaded.status == "TODO"

    def test_load_all_empty(self, task_manager):
        """Load all tasks from empty directory."""
        tasks = task_manager.load_all()
        assert tasks == []

    def test_load_all_multiple(self, task_manager):
        """Load all tasks, sorted by ID."""
        task_manager.create(Task(id="TASK-003", title="Third"))
        task_manager.create(Task(id="TASK-001", title="First"))
        task_manager.create(Task(id="TASK-002", title="Second"))

        tasks = task_manager.load_all()
        assert len(tasks) == 3
        assert [t.id for t in tasks] == ["TASK-001", "TASK-002", "TASK-003"]


class TestTaskManagerUpdateStatus:
    """Test status updates."""

    def test_update_status_valid(self, task_manager):
        """Update task status to a valid value."""
        task_manager.create(Task(id="TASK-001", title="Test", status="TODO"))
        task_manager.update_status("TASK-001", "IN_PROGRESS", note="Started work")

        loaded = task_manager.load("TASK-001")
        assert loaded.status == "IN_PROGRESS"
        assert any("Started work" in entry for entry in loaded.log_entries)

    def test_update_status_invalid(self, task_manager):
        """Invalid status raises ValueError."""
        task_manager.create(Task(id="TASK-001", title="Test"))
        with pytest.raises(ValueError):
            task_manager.update_status("TASK-001", "INVALID_STATUS")

    def test_update_status_without_note(self, task_manager):
        """Update status generates default log entry."""
        task_manager.create(Task(id="TASK-001", title="Test", status="TODO"))
        task_manager.update_status("TASK-001", "DONE")

        loaded = task_manager.load("TASK-001")
        assert loaded.status == "DONE"
        assert any("Status → DONE" in entry for entry in loaded.log_entries)

    def test_update_nonexistent_task(self, task_manager):
        """Updating nonexistent task raises TaskNotFoundError."""
        with pytest.raises(TaskNotFoundError):
            task_manager.update_status("TASK-999", "DONE")


class TestTaskManagerDelete:
    """Test task deletion."""

    def test_delete_task(self, task_manager, temp_tasks_dir):
        """Delete a task file."""
        task_manager.create(Task(id="TASK-001", title="Test"))
        assert (temp_tasks_dir / "TASK-001.md").exists()

        task_manager.delete("TASK-001")
        assert not (temp_tasks_dir / "TASK-001.md").exists()

    def test_delete_nonexistent_task(self, task_manager):
        """Deleting nonexistent task raises TaskNotFoundError."""
        with pytest.raises(TaskNotFoundError):
            task_manager.delete("TASK-999")


class TestTaskManagerQuery:
    """Test query methods."""

    def test_by_status(self, task_manager):
        """Filter tasks by status."""
        task_manager.create(Task(id="TASK-001", title="Task 1", status="TODO"))
        task_manager.create(Task(id="TASK-002", title="Task 2", status="TODO"))
        task_manager.create(Task(id="TASK-003", title="Task 3", status="DONE"))

        todos = task_manager.by_status("TODO")
        assert len(todos) == 2
        assert all(t.status == "TODO" for t in todos)

    def test_next_todo_none(self, task_manager):
        """Return None when no TODO tasks."""
        next_task = task_manager.next_todo()
        assert next_task is None

    def test_next_todo_single(self, task_manager):
        """Return single TODO task."""
        task_manager.create(Task(id="TASK-001", title="Only Todo", status="TODO"))
        next_task = task_manager.next_todo()
        assert next_task.id == "TASK-001"

    def test_next_todo_priority_order(self, task_manager):
        """Return highest-priority TODO first."""
        task_manager.create(Task(id="TASK-001", title="Low", status="TODO", priority="low"))
        task_manager.create(Task(id="TASK-002", title="High", status="TODO", priority="high"))
        task_manager.create(Task(id="TASK-003", title="Medium", status="TODO", priority="medium"))

        next_task = task_manager.next_todo()
        assert next_task.id == "TASK-002"  # highest priority


class TestTaskManagerRoundTrip:
    """Test that serialization and parsing are inverses."""

    def test_round_trip_minimal(self, task_manager):
        """Round-trip minimal task."""
        original = Task(id="TASK-001", title="Minimal")
        task_manager.create(original)
        loaded = task_manager.load("TASK-001")

        assert loaded.id == original.id
        assert loaded.title == original.title
        assert loaded.priority == "medium"  # default
        assert loaded.status == "TODO"  # default

    def test_round_trip_full(self, task_manager):
        """Round-trip task with all fields."""
        original = Task(
            id="TASK-005",
            title="Complex Task",
            sprint="sprint-002",
            priority="high",
            assigned="charlie",
            status="IN_REVIEW",
            created="2026-02-25",
            updated="2026-02-26",
            context="Multi-line\ncontext here",
            requirements=["first", "second", "third"],
            files_to_modify=["file1.py", "file2.py"],
            constraints=["constraint 1", "constraint 2"],
            acceptance_criteria=["[ ] criterion 1", "[ ] criterion 2"],
            log_entries=["- 2026-02-25: Created", "- 2026-02-26: In review"],
        )
        task_manager.create(original)
        loaded = task_manager.load("TASK-005")

        assert loaded.id == original.id
        assert loaded.title == original.title
        assert loaded.sprint == original.sprint
        assert loaded.priority == original.priority
        assert loaded.assigned == original.assigned
        assert loaded.status == original.status
        assert loaded.created == original.created
        # TaskManager.create() always sets updated to today, so check it's a valid ISO date
        assert re.match(r"\d{4}-\d{2}-\d{2}", loaded.updated), f"Invalid date format: {loaded.updated}"
        assert loaded.context == original.context
        assert loaded.requirements == original.requirements
        assert loaded.files_to_modify == original.files_to_modify
        assert loaded.constraints == original.constraints
        assert loaded.acceptance_criteria == original.acceptance_criteria
        assert loaded.log_entries == original.log_entries

    def test_round_trip_empty_lists(self, task_manager):
        """Round-trip task with empty list sections."""
        original = Task(
            id="TASK-010",
            title="Empty Lists",
            requirements=[],
            files_to_modify=[],
            constraints=[],
            acceptance_criteria=[],
            log_entries=[],
        )
        task_manager.create(original)
        loaded = task_manager.load("TASK-010")

        assert loaded.requirements == []
        assert loaded.files_to_modify == []
        assert loaded.constraints == []
        assert loaded.acceptance_criteria == []
        assert loaded.log_entries == []


class TestTaskManagerParseError:
    """Test error handling in parsing."""

    def test_parse_malformed_heading(self, task_manager, temp_tasks_dir):
        """Malformed heading raises TaskParseError."""
        # Write invalid file without proper heading
        path = temp_tasks_dir / "TASK-BAD.md"
        path.write_text("Some random content", encoding="utf-8")

        with pytest.raises(TaskParseError):
            task_manager._parse(path)

    def test_load_all_skips_malformed(self, task_manager, temp_tasks_dir):
        """load_all skips malformed files."""
        # Good task
        task_manager.create(Task(id="TASK-001", title="Good"))

        # Bad task
        bad_path = temp_tasks_dir / "TASK-002.md"
        bad_path.write_text("Invalid content", encoding="utf-8")

        tasks = task_manager.load_all()
        assert len(tasks) == 1
        assert tasks[0].id == "TASK-001"
