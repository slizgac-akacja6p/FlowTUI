"""Limits panel widget — displays FlowTUI call counter vs budget."""
from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.widget import Widget

from flowtui.config.loader import load_config, ConfigNotFoundError
from flowtui.analytics.storage import AnalyticsStorage


class LimitsPanel(Widget):
    """Displays FlowTUI call budget tracking.

    Shows daily call counter per tool vs configured limits.
    Loads config and analytics in on_mount().
    """

    DEFAULT_CSS = ""

    def __init__(self, *args, **kwargs):
        """Initialize LimitsPanel with usage tracking state."""
        super().__init__(*args, **kwargs)
        self._usage = {"claude": 0, "codex": 0, "gemini": 0}
        self._limits = {"claude": 10, "codex": 5, "gemini": 10}

    def compose(self) -> ComposeResult:
        """Compose limits panel with title and counter placeholder."""
        yield Label("LIMITS (FlowTUI calls today)", id="limits-title")
        yield Static("Loading...", id="limits-counter")

    def on_mount(self) -> None:
        """Load config and analytics, display limits and today's usage.

        Handles missing config gracefully with fallback text.
        Stores state in _usage and _limits for increment_counter() to use.
        """
        counter = self.query_one("#limits-counter", Static)

        try:
            # Get project root from app or use current directory
            project_root = getattr(self.app, "project_root", None) or Path.cwd()

            # Load config to get daily limits
            config = load_config(project_root)

            # Load analytics to count today's calls per tool
            analytics_path = project_root / ".flowtui" / "analytics.jsonl"
            storage = AnalyticsStorage(analytics_path)
            today_records = storage.read_today()

            # Count calls per tool and store in instance state
            for tool in ["claude", "codex", "gemini"]:
                self._usage[tool] = sum(
                    1 for record in today_records
                    if record.get("tool") == tool
                )

            # Get limits from config and store in instance state
            self._limits["claude"] = config.limits.claude_daily_budget
            self._limits["codex"] = config.limits.codex_daily_budget
            self._limits["gemini"] = config.limits.gemini_daily_budget

            # Format and display
            self._update_display(counter)

        except ConfigNotFoundError:
            counter.update("Limits: config not found")
        except Exception as e:
            # Catch any other errors (file access, parsing, etc.)
            counter.update(f"Limits: error — {type(e).__name__}")

    def _update_display(self, counter) -> None:
        """Update counter display from stored _usage and _limits state."""
        display_parts = []
        for tool in ["claude", "codex", "gemini"]:
            count = self._usage[tool]
            limit = self._limits[tool]
            display_parts.append(f"{tool}: {count} / {limit}")

        display_text = " | ".join(display_parts)
        counter.update(display_text)

    def increment_counter(self, tool: str = "claude") -> None:
        """Increment call counter for specified tool.

        Args:
            tool: Tool name to increment ("claude", "codex", or "gemini").
        """
        if tool in self._usage:
            self._usage[tool] += 1
            counter = self.query_one("#limits-counter", Static)
            self._update_display(counter)
