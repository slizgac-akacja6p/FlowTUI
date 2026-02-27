"""TUI screens and routing."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Label, OptionList


class MainScreen(Screen):
    """Main application screen.

    In M1, this is a placeholder for screen routing and state management.
    Screen composition is delegated to FlowTUIApp in app.py.
    M2+ will extend this with navigation logic and screen stack management.
    """

    pass


class CommandPickerScreen(ModalScreen):
    """Modal command picker — press F1 to open, Escape to close.

    Selecting a command dismisses the modal and returns the command prefix
    so the caller can populate the input field without executing immediately.
    This lets users discover and compose commands without memorising syntax.
    """

    COMMANDS = [
        ("plan <description>", "plan "),
        ("code TASK-XXX", "code "),
        ("review TASK-XXX", "review "),
        ("run TASK-XXX", "run "),
        ("run sprint", "run sprint"),
        ("merge [TASK-XXX]", "merge"),
        ("chat", "chat"),
        ("stats", "stats"),
        ("stats --export csv", "stats --export csv"),
        ("stats --export json", "stats --export json"),
        ("status", "status"),
        ("cc <prompt>", "cc "),
        ("codex <prompt>", "codex "),
        ("gemini <prompt>", "gemini "),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-container"):
            yield Label("Commands (Enter to select, Esc to close)", id="picker-title")
            yield OptionList(*[label for label, _ in self.COMMANDS], id="picker-list")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        _, value = self.COMMANDS[event.option_index]
        self.dismiss(value)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
