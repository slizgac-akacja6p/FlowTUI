"""Sprint panel widget — displays sprint summary and progress."""
from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.widget import Widget


class SprintPanel(Widget):
    """Displays active sprint summary and task metrics.

    Data loading (sprint stats, progress bars) deferred to M2.
    M1 scope: layout skeleton only with placeholder summary.
    """

    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        """Compose sprint panel with title and summary placeholder."""
        yield Label("SPRINT", id="sprint-title")
        yield Static("No sprint active", id="sprint-summary")
