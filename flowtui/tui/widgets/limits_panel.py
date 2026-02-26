"""Limits panel widget — displays FlowTUI call counter vs budget."""
from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.widget import Widget


class LimitsPanel(Widget):
    """Displays FlowTUI call budget tracking.

    Shows daily call counter for Claude API vs configured limits.
    Data loading deferred to M2 via event handlers.
    M1 scope: layout skeleton only with placeholder counter.
    """

    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        """Compose limits panel with title and counter placeholder."""
        yield Label("LIMITS (FlowTUI calls today)", id="limits-title")
        yield Static("0 / — calls", id="limits-counter")

    def increment_counter(self) -> None:
        """Increment call counter display."""
        counter = self.query_one("#limits-counter", Static)
        # Parse current "N / M" format, increment N
        text = counter.renderable
        try:
            parts = str(text).split(" / ")
            n = int(parts[0]) + 1
            rest = parts[1] if len(parts) > 1 else "—"
            counter.update(f"{n} / {rest}")
        except (ValueError, IndexError):
            counter.update("1 / —")
