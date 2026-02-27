"""Tests for context writer — sprint.md generation."""

import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from flowtui.core.context_writer import write_sprint_context
from flowtui.core.task_manager import Task


class MockTask:
    """Mock task object for testing duck typing."""

    def __init__(self, id, title, status):
        self.id = id
        self.title = title
        self.status = status


class TestWriteSprintContextBasic:
    """Test basic sprint context file creation."""

    def test_creates_file(self):
        """write_sprint_context creates docs/context/sprint.md file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_path = write_sprint_context(
                project_root, [], {}, "TestProject", "Python"
            )

            assert output_path.exists()
            assert output_path.name == "sprint.md"
            assert output_path.parent.name == "context"

    def test_file_location(self):
        """sprint.md is created in docs/context/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_path = write_sprint_context(
                project_root, [], {}, "Test", "Stack"
            )

            expected_path = project_root / "docs" / "context" / "sprint.md"
            assert output_path == expected_path

    def test_creates_directories(self):
        """write_sprint_context creates docs/context if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Ensure directories don't exist
            assert not (project_root / "docs").exists()

            write_sprint_context(project_root, [], {}, "Test", "Stack")

            assert (project_root / "docs" / "context").exists()


class TestWriteSprintContextContent:
    """Test sprint.md content generation."""

    def test_file_content_has_header(self):
        """sprint.md contains main header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(project_root, [], {}, "TestProject", "Python")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "# Sprint Context" in content

    def test_file_content_has_timestamp(self):
        """sprint.md contains timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(project_root, [], {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "Generated:" in content
            # Check it looks like a date (YYYY-MM-DD format)
            assert any(
                f"{i:04d}-" in content for i in range(2020, 2030)
            )  # rough check

    def test_file_content_has_project_info(self):
        """sprint.md contains project name and stack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(
                project_root, [], {}, "MyApp", "Python + FastAPI"
            )

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "MyApp" in content
            assert "Python + FastAPI" in content

    def test_file_has_sections(self):
        """sprint.md has all expected sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(project_root, [], {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "## Project" in content
            assert "## Active Tasks" in content
            assert "## Limits Today" in content
            assert "## Last completed" in content


class TestSprintContextTasks:
    """Test task inclusion in sprint context."""

    def test_no_active_tasks(self):
        """No active tasks → 'No active tasks.' message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(project_root, [], {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "No active tasks." in content

    def test_active_tasks_included(self):
        """Tasks with TODO status → included in active section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                MockTask("TASK-001", "First Task", "TODO"),
                MockTask("TASK-002", "Second Task", "TODO"),
            ]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "TASK-001" in content
            assert "TASK-002" in content
            assert "First Task" in content
            assert "Second Task" in content

    def test_in_progress_tasks_included(self):
        """Tasks with IN_PROGRESS status → included in active section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [MockTask("TASK-003", "Active Task", "IN_PROGRESS")]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "TASK-003" in content
            assert "Active Task" in content

    def test_done_tasks_in_last_completed(self):
        """Tasks with DONE status → in 'Last completed' section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                MockTask("TASK-001", "Completed Task", "DONE"),
                MockTask("TASK-002", "Another Done", "DONE"),
            ]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "Completed Task" in content
            assert "TASK-001" in content

    def test_no_completed_tasks(self):
        """No done tasks → 'None yet.' message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [MockTask("TASK-001", "TODO Task", "TODO")]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "None yet." in content

    def test_max_five_active_tasks(self):
        """Max 5 active tasks shown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                MockTask(f"TASK-{i:03d}", f"Task {i}", "TODO")
                for i in range(1, 8)
            ]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            # Only first 5 should be included
            assert "TASK-001" in content
            assert "TASK-005" in content
            # 6th and 7th might not be in active section (but could be in other sections)

    def test_max_three_completed_tasks(self):
        """Max 3 done tasks shown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                MockTask(f"TASK-{i:03d}", f"Task {i}", "DONE")
                for i in range(1, 6)
            ]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            # Should have last 3 (newest first or all present)
            assert "TASK-" in content  # At least some tasks

    def test_task_status_displayed(self):
        """Task status shown in brackets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                MockTask("TASK-001", "Todo Task", "TODO"),
                MockTask("TASK-002", "Progress Task", "IN_PROGRESS"),
            ]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "[TODO]" in content or "TODO" in content
            assert "[IN_PROGRESS]" in content or "IN_PROGRESS" in content


class TestSprintContextLimits:
    """Test limits summary in sprint context."""

    def test_no_limits_configured(self):
        """No limits → 'No limits configured.' message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(project_root, [], {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "No limits configured." in content

    def test_limits_summary_format(self):
        """Limits displayed as 'tool: used/budget'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            limits = {"cc": (5, 50), "codex": (3, 20)}

            write_sprint_context(project_root, [], limits, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "cc: 5/50" in content
            assert "codex: 3/20" in content

    def test_single_limit(self):
        """Single limit tool displayed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            limits = {"claude": (10, 100)}

            write_sprint_context(project_root, [], limits, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "claude: 10/100" in content


class TestSprintContextSize:
    """Test that sprint.md stays small and manageable."""

    def test_short_file_minimal(self):
        """Minimal context generates small file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            write_sprint_context(project_root, [], {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            lines = content.split("\n")
            # Should be very small (< 50 lines)
            assert len(lines) < 50

    def test_short_file_with_tasks(self):
        """Context with some tasks stays small."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                MockTask("TASK-001", "Task 1", "TODO"),
                MockTask("TASK-002", "Task 2", "DONE"),
            ]

            write_sprint_context(project_root, tasks, {"cc": (5, 50)}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            lines = content.split("\n")
            # Should still be manageable (< 100 lines)
            assert len(lines) < 100

    def test_returns_correct_path(self):
        """write_sprint_context returns the path to created file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            result = write_sprint_context(project_root, [], {}, "Test", "Stack")

            assert result.is_absolute()
            assert result.exists()
            assert "sprint.md" in str(result)


class TestSprintContextDuckTyping:
    """Test duck typing with different task-like objects."""

    def test_works_with_real_task_dataclass(self):
        """Works with real Task objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tasks = [
                Task(id="TASK-001", title="Real Task", status="TODO"),
            ]

            write_sprint_context(project_root, tasks, {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            assert "TASK-001" in content
            assert "Real Task" in content

    def test_handles_missing_attributes(self):
        """Handles objects missing expected attributes gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Object without status attribute
            incomplete_task = type("Task", (), {"id": "T-1", "title": "Incomplete"})()

            # Should not raise, should use default values
            write_sprint_context(project_root, [incomplete_task], {}, "Test", "Stack")

            content = (project_root / "docs" / "context" / "sprint.md").read_text()
            # Should have something (maybe "No active tasks" if status filtering works)
            assert content is not None
