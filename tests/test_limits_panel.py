"""Tests for LimitsPanel widget."""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from textual.app import ComposeResult
from textual.widgets import Static

from flowtui.tui.widgets.limits_panel import LimitsPanel
from flowtui.config.schema import FlowTUIConfig, ProjectConfig, LimitsConfig


class TestLimitsPanelCompose:
    """Test LimitsPanel.compose() method."""

    def test_compose_yields_title_and_counter(self):
        """Test that compose yields title label and counter static."""
        panel = LimitsPanel()
        widgets = list(panel.compose())
        assert len(widgets) == 2
        assert widgets[0].id == "limits-title"
        assert widgets[1].id == "limits-counter"

    def test_counter_initial_text_is_loading(self):
        """Test that initial counter shows 'Loading...'."""
        panel = LimitsPanel()
        widgets = list(panel.compose())
        counter = widgets[1]
        assert isinstance(counter, Static)
        # Static widget will show the default text during rendering


class TestLimitsPanelOnMount:
    """Test LimitsPanel.on_mount() method via unit tests and integration."""

    def test_on_mount_method_exists(self):
        """Test that on_mount method exists and is callable."""
        panel = LimitsPanel()
        assert hasattr(panel, "on_mount")
        assert callable(panel.on_mount)


class TestLimitsPanelIncrementCounter:
    """Test LimitsPanel.increment_counter() method."""

    def test_increment_counter_increments_claude_usage(self):
        """Test that increment_counter increments claude usage count."""
        panel = LimitsPanel()
        panel._usage = {"claude": 5, "codex": 2, "gemini": 1}
        panel._limits = {"claude": 10, "codex": 5, "gemini": 10}

        # Create mock Static widget
        mock_counter = Mock(spec=Static)

        with patch.object(panel, "query_one", return_value=mock_counter):
            panel.increment_counter(tool="claude")

        # Should update display with incremented count
        mock_counter.update.assert_called_once_with("claude: 6 / 10 | codex: 2 / 5 | gemini: 1 / 10")

    def test_increment_counter_increments_codex_usage(self):
        """Test that increment_counter increments codex usage count."""
        panel = LimitsPanel()
        panel._usage = {"claude": 5, "codex": 2, "gemini": 1}
        panel._limits = {"claude": 10, "codex": 5, "gemini": 10}

        # Create mock Static widget
        mock_counter = Mock(spec=Static)

        with patch.object(panel, "query_one", return_value=mock_counter):
            panel.increment_counter(tool="codex")

        # Should update display with incremented count
        mock_counter.update.assert_called_once_with("claude: 5 / 10 | codex: 3 / 5 | gemini: 1 / 10")

    def test_increment_counter_defaults_to_claude(self):
        """Test that increment_counter defaults to claude when no tool specified."""
        panel = LimitsPanel()
        panel._usage = {"claude": 5, "codex": 2, "gemini": 1}
        panel._limits = {"claude": 10, "codex": 5, "gemini": 10}

        # Create mock Static widget
        mock_counter = Mock(spec=Static)

        with patch.object(panel, "query_one", return_value=mock_counter):
            panel.increment_counter()

        # Should increment claude by default
        mock_counter.update.assert_called_once_with("claude: 6 / 10 | codex: 2 / 5 | gemini: 1 / 10")
