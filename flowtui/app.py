"""FlowTUI Textual application — main TUI entrypoint."""
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Input

from flowtui.tui.widgets import (
    TaskPanel,
    LimitsPanel,
    SprintPanel,
    TerminalPanel,
)


class FlowTUIApp(App):
    """Main FlowTUI TUI application.

    4-panel layout:
    - Task panel (70% width, left)
    - Limits & Sprint panels (30% width, stacked right)
    - Terminal panel (scrollable logs, bottom)
    - Command input (at very bottom)

    Styling via flowtui/tui/styles.tcss.
    """

    CSS_PATH = Path(__file__).parent / "tui/styles.tcss"

    def compose(self) -> ComposeResult:
        """Compose main layout with header, panels, and footer."""
        yield Header()

        with Horizontal(id="main-content"):
            yield TaskPanel(id="task-panel")

            with Vertical(id="right-panel"):
                yield LimitsPanel(id="limits-panel")
                yield SprintPanel(id="sprint-panel")

        yield TerminalPanel(id="terminal-panel")
        yield Input(placeholder="Command...", id="cmd-input")

        yield Footer()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input submission.

        Dispatching logic deferred to M2+ event handlers.
        """
        pass
