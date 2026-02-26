"""Terminal panel widget — scrollable log output for execution and debug info."""
from textual.app import ComposeResult
from textual.widgets import Log
from textual.widget import Widget


class TerminalPanel(Widget):
    """Displays scrollable terminal-like output for logs and execution results.

    M1 scope: renders empty Log widget (populated in M2 via message posting).
    Buffering and async log writing deferred to M2 event handlers.
    """

    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        """Compose terminal panel with scrollable log."""
        yield Log(id="terminal-log")
