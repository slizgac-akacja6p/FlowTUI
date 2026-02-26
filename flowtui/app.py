"""FlowTUI Textual application."""
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input


class FlowTUIApp(App):
    """Main FlowTUI application."""

    CSS_PATH = "tui/styles.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Input(placeholder="> enter command...")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        pass  # dispatch_command implemented in M1 T1.8
