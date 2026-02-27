"""Tests for FlowTUI config system — schema validation and loading."""
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from flowtui.config import (
    ConfigNotFoundError,
    FlowTUIConfig,
    LimitsConfig,
    ProjectConfig,
    StartupConfig,
    ToolConfig,
    find_project_root,
    load_config,
)


class TestProjectConfig:
    """Test ProjectConfig schema."""

    def test_project_config_minimal(self):
        """Create ProjectConfig with minimal fields."""
        cfg = ProjectConfig(name="Test", stack="Python")
        assert cfg.name == "Test"
        assert cfg.stack == "Python"
        assert cfg.description == ""

    def test_project_config_frozen(self):
        """ProjectConfig is frozen (immutable)."""
        cfg = ProjectConfig(name="Test", stack="Python")
        with pytest.raises(ValidationError):
            cfg.name = "Other"

    def test_project_config_all_fields(self):
        """Create ProjectConfig with all fields."""
        cfg = ProjectConfig(
            name="MyApp",
            stack="Python/Textual",
            description="A terminal app",
        )
        assert cfg.name == "MyApp"
        assert cfg.stack == "Python/Textual"
        assert cfg.description == "A terminal app"


class TestToolConfig:
    """Test ToolConfig schema."""

    def test_tool_config_minimal(self):
        """Create ToolConfig with minimal fields."""
        cfg = ToolConfig(command="cc")
        assert cfg.command == "cc"
        assert cfg.flags == ""
        assert cfg.planning_prompt == ""

    def test_tool_config_frozen(self):
        """ToolConfig is frozen."""
        cfg = ToolConfig(command="cc", flags="-p")
        with pytest.raises(ValidationError):
            cfg.command = "other"

    def test_tool_config_all_fields(self):
        """Create ToolConfig with all fields."""
        cfg = ToolConfig(
            command="cc",
            flags="-p project.md",
            planning_prompt="Plan this",
            coding_prompt="Code this",
            review_prompt="Review this",
        )
        assert cfg.command == "cc"
        assert cfg.flags == "-p project.md"
        assert cfg.planning_prompt == "Plan this"


class TestLimitsConfig:
    """Test LimitsConfig schema."""

    def test_limits_config_defaults(self):
        """LimitsConfig has default budgets."""
        cfg = LimitsConfig()
        assert cfg.claude_daily_budget == 15
        assert cfg.codex_daily_budget == 5
        assert cfg.gemini_daily_budget == 30

    def test_limits_config_custom(self):
        """LimitsConfig accepts custom budgets."""
        cfg = LimitsConfig(
            claude_daily_budget=20,
            codex_daily_budget=10,
            gemini_daily_budget=50,
        )
        assert cfg.claude_daily_budget == 20
        assert cfg.codex_daily_budget == 10
        assert cfg.gemini_daily_budget == 50

    def test_limits_config_frozen(self):
        """LimitsConfig is frozen."""
        cfg = LimitsConfig()
        with pytest.raises(ValidationError):
            cfg.claude_daily_budget = 30


class TestStartupConfig:
    """Test StartupConfig schema."""

    def test_startup_config_defaults(self):
        """StartupConfig has sensible defaults."""
        cfg = StartupConfig()
        assert cfg.auto_update is True
        assert cfg.update_timeout == 60
        assert cfg.skip_if_recent == 3600

    def test_startup_config_custom(self):
        """StartupConfig accepts custom values."""
        cfg = StartupConfig(
            auto_update=False,
            update_timeout=120,
            skip_if_recent=7200,
        )
        assert cfg.auto_update is False
        assert cfg.update_timeout == 120
        assert cfg.skip_if_recent == 7200

    def test_startup_config_frozen(self):
        """StartupConfig is frozen."""
        cfg = StartupConfig()
        with pytest.raises(ValidationError):
            cfg.auto_update = False


class TestFlowTUIConfig:
    """Test FlowTUIConfig schema."""

    def test_flowtui_config_minimal(self):
        """Create FlowTUIConfig with minimal fields."""
        cfg = FlowTUIConfig(
            project=ProjectConfig(name="Test", stack="Python")
        )
        assert cfg.project.name == "Test"
        assert cfg.tools == {}
        assert cfg.limits.claude_daily_budget == 15

    def test_flowtui_config_with_tools(self):
        """Create FlowTUIConfig with tools."""
        cfg = FlowTUIConfig(
            project=ProjectConfig(name="Test", stack="Python"),
            tools={
                "cc": ToolConfig(command="cc"),
                "claude": ToolConfig(command="claude", flags="-p"),
            },
        )
        assert "cc" in cfg.tools
        assert "claude" in cfg.tools
        assert cfg.tools["cc"].command == "cc"

    def test_flowtui_config_frozen(self):
        """FlowTUIConfig is frozen."""
        cfg = FlowTUIConfig(
            project=ProjectConfig(name="Test", stack="Python")
        )
        with pytest.raises(ValidationError):
            cfg.project = None


class TestLoadConfig:
    """Test load_config function."""

    def test_load_config_valid(self):
        """Load valid config from .flowtui/config.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            flowtui_dir = root / ".flowtui"
            flowtui_dir.mkdir()

            config_content = """
[project]
name = "TestApp"
stack = "Python/Textual"
description = "A test app"

[limits]
claude_daily_budget = 20

[startup]
auto_update = false
"""
            (flowtui_dir / "config.toml").write_text(config_content)

            cfg = load_config(root)
            assert cfg.project.name == "TestApp"
            assert cfg.project.stack == "Python/Textual"
            assert cfg.limits.claude_daily_budget == 20
            assert cfg.startup.auto_update is False

    def test_load_config_missing_file(self):
        """Missing .flowtui/config.toml raises ConfigNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with pytest.raises(ConfigNotFoundError):
                load_config(root)

    def test_load_config_invalid_toml(self):
        """Invalid TOML raises ValidationError or similar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            flowtui_dir = root / ".flowtui"
            flowtui_dir.mkdir()

            (flowtui_dir / "config.toml").write_text("invalid {{{ toml")

            with pytest.raises(Exception):  # Could be ValidationError or parse error
                load_config(root)

    def test_load_config_missing_required_fields(self):
        """Config missing required [project] raises ValidationError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            flowtui_dir = root / ".flowtui"
            flowtui_dir.mkdir()

            config_content = "[limits]\nClaude_daily_budget = 15"
            (flowtui_dir / "config.toml").write_text(config_content)

            with pytest.raises(ValidationError):
                load_config(root)


class TestFindProjectRoot:
    """Test find_project_root function."""

    def test_find_project_root_in_current(self):
        """find_project_root finds .flowtui in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            flowtui_dir = root / ".flowtui"
            flowtui_dir.mkdir()
            (flowtui_dir / "config.toml").write_text("[project]\nname='Test'\nstack='Python'")

            result = find_project_root(root)
            assert result.resolve() == root.resolve()

    def test_find_project_root_in_parent(self):
        """find_project_root walks up to parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            flowtui_dir = root / ".flowtui"
            flowtui_dir.mkdir()
            (flowtui_dir / "config.toml").write_text("[project]\nname='Test'\nstack='Python'")

            # Create subdirectory and search from there
            subdir = root / "src" / "app"
            subdir.mkdir(parents=True)

            result = find_project_root(subdir)
            assert result.resolve() == root.resolve()

    def test_find_project_root_not_found(self):
        """find_project_root raises ConfigNotFoundError if not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with pytest.raises(ConfigNotFoundError):
                find_project_root(root)

    def test_find_project_root_uses_cwd_by_default(self):
        """find_project_root uses current directory if start is None."""
        # This test uses the actual current working directory
        # We'll just verify it handles the default case without error
        # In a real test environment, this would fail unless .flowtui exists
        try:
            result = find_project_root(None)
            assert isinstance(result, Path)
        except ConfigNotFoundError:
            # Expected if .flowtui doesn't exist in parent directories
            pass
