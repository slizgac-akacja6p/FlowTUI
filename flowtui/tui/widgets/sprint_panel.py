"""Sprint panel widget — displays sprint summary and progress."""
from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.widget import Widget


class SprintPanel(Widget):
    """Displays active sprint summary and task metrics.

    Loads task list from project docs/tasks/ directory and displays
    counts of TODO, IN_PROGRESS, and DONE tasks.
    """

    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        """Compose sprint panel with title and summary placeholder."""
        yield Label("SPRINT", id="sprint-title")
        yield Static("No sprint data", id="sprint-summary")

    def on_mount(self) -> None:
        """Load sprint data and update summary with task counts.

        Counts tasks by status (TODO, IN_PROGRESS, DONE) from docs/tasks/
        and displays as "TODO: N | IN_PROGRESS: N | DONE: N/total".
        """
        try:
            from pathlib import Path
            from flowtui.core.task_manager import TaskManager

            # Get tasks directory from project root (stored in app) with fallback
            project_root = getattr(self.app, "project_root", None)
            if project_root is None:
                self.query_one("#sprint-summary", Static).update("No project root")
                return

            tasks_dir = project_root / "docs" / "tasks"

            if not tasks_dir.exists():
                self.query_one("#sprint-summary", Static).update("No sprint data")
                return

            task_mgr = TaskManager(tasks_dir)
            tasks = task_mgr.load_all()

            if not tasks:
                self.query_one("#sprint-summary", Static).update("No sprint data")
                return

            # Count tasks by status
            todo_count = sum(1 for t in tasks if t.status == "TODO")
            in_progress_count = sum(1 for t in tasks if t.status == "IN_PROGRESS")
            done_count = sum(1 for t in tasks if t.status == "DONE")
            total = len(tasks)

            # Update summary
            summary = f"TODO: {todo_count} | IN_PROGRESS: {in_progress_count} | DONE: {done_count}/{total}"
            self.query_one("#sprint-summary", Static).update(summary)

        except Exception as e:
            self.query_one("#sprint-summary", Static).update(f"Error: {e}")
