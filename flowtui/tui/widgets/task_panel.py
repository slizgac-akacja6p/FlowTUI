"""Task panel widget — displays current tasks (data loading deferred to M2)."""
import threading
from pathlib import Path

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Label, Static
from textual.widget import Widget

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class TasksChanged(Message):
    """Posted when task files change on disk."""

    pass


class TaskFileHandler(FileSystemEventHandler):
    """Watchdog handler for task file changes.

    Monitors task directory and posts TasksChanged message to app.
    Implements debouncing via threading.Timer to avoid multiple events
    from the same file operation (e.g., write → metadata update).
    """

    def __init__(self, app_ref, debounce_sec: float = 0.5):
        """Initialize handler with app reference and debounce window.

        Args:
            app_ref: Reference to Textual app for posting messages.
            debounce_sec: Debounce window in seconds (default 0.5s).
        """
        super().__init__()
        self._app = app_ref
        self._debounce_sec = debounce_sec
        self._timer = None
        self._stopped = threading.Event()

    def on_any_event(self, event):
        """Handle any filesystem event with debouncing.

        Resets debounce timer on each event; posts message only after
        debounce window expires with no new events.

        Args:
            event: FileSystemEvent from watchdog.
        """
        # Exit early if handler has been stopped (widget unmounted)
        if self._stopped.is_set():
            return

        # Cancel existing timer if present
        if self._timer is not None:
            self._timer.cancel()

        # Schedule message post after debounce window
        def post_message():
            self._app.call_from_thread(self._app.post_message, TasksChanged())

        self._timer = threading.Timer(self._debounce_sec, post_message)
        self._timer.daemon = True
        self._timer.start()


class TaskPanel(Widget):
    """Displays current tasks from the active project.

    Data loading and task list rendering deferred to M2.
    M1 scope: layout skeleton only with placeholder content.

    Watches task directory for changes and reloads task list on disk updates.
    """

    DEFAULT_CSS = ""

    def __init__(self, *args, tasks_directory: Path | None = None, **kwargs):
        """Initialize TaskPanel with optional tasks directory.

        Args:
            tasks_directory: Directory to watch for task files.
                            If None, no file watching is enabled.
            *args, **kwargs: Passed to parent Widget.
        """
        super().__init__(*args, **kwargs)
        self._tasks_directory = tasks_directory
        self._observer = None
        self._file_handler = None

    def compose(self) -> ComposeResult:
        """Compose task panel with title and placeholder."""
        yield Label("TASKS", id="task-panel-title")
        yield Static("No tasks loaded", id="task-list-placeholder")

    def on_mount(self) -> None:
        """Start watchdog observer when widget mounts.

        If no tasks_directory provided, observer is skipped.
        """
        if self._tasks_directory is None or not self._tasks_directory.exists():
            return

        # Create observer and file handler
        self._observer = Observer()
        self._file_handler = TaskFileHandler(self.app, debounce_sec=0.5)

        # Watch tasks directory
        self._observer.schedule(
            self._file_handler,
            str(self._tasks_directory),
            recursive=False,
        )

        # Start observer in daemon mode (stops when app exits)
        self._observer.start()

    def on_unmount(self) -> None:
        """Stop watchdog observer when widget unmounts."""
        # Mark handler as stopped BEFORE stopping observer
        if self._file_handler is not None:
            self._file_handler._stopped.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None

    async def on_tasks_changed(self, message: TasksChanged) -> None:
        """Handle TasksChanged message by refreshing task list.

        Args:
            message: TasksChanged message posted by file watcher.
        """
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        """Reload task list from disk and display as table.

        Loads all TASK-*.md files from tasks directory and renders a table
        with ID, Status, Priority, and Title columns.
        """
        task_list = self.query_one("#task-list-placeholder", Static)

        # Skip if no tasks directory configured
        if self._tasks_directory is None or not self._tasks_directory.exists():
            task_list.update("Tasks refreshed: no tasks found in docs/tasks/")
            return

        try:
            from flowtui.core.task_manager import TaskManager

            task_mgr = TaskManager(self._tasks_directory)
            tasks = task_mgr.load_all()

            if not tasks:
                task_list.update("Tasks refreshed: no tasks found in docs/tasks/")
                return

            # Build table: ID | Status | Priority | Title
            lines = ["ID | Status | Priority | Title"]
            lines.append("-" * 60)
            for task in tasks:
                lines.append(f"{task.id} | {task.status:11} | {task.priority:8} | {task.title}")

            task_list.update("Tasks refreshed:\n" + "\n".join(lines))

        except Exception as e:
            task_list.update(f"Tasks refreshed with error: {e}")
