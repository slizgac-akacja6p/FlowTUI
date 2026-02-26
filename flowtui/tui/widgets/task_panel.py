"""Task panel widget — displays current tasks (data loading deferred to M2)."""
from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.widget import Widget


class TaskPanel(Widget):
    """Displays current tasks from the active project.

    Data loading and task list rendering deferred to M2.
    M1 scope: layout skeleton only with placeholder content.
    """

    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        """Compose task panel with title and placeholder."""
        yield Label("TASKS", id="task-panel-title")
        yield Static("No tasks loaded", id="task-list-placeholder")
