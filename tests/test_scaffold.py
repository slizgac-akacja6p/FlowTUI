"""Tests for project scaffolding — flowtui init."""
import tempfile
from pathlib import Path
import json

import pytest

from flowtui.scaffold.init import scaffold_project, AlreadyInitializedError


class TestScaffoldProject:
    """Test scaffold_project function."""

    def test_scaffold_creates_directory_structure(self):
        """scaffold_project creates all required directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root, project_name="TestApp", stack="Python/Textual")

            # Check directories exist
            assert (root / ".flowtui").exists()
            assert (root / "PM").exists()
            assert (root / "PM" / "tasks").exists()
            assert (root / "docs").exists()
            assert (root / "docs" / "context").exists()
            assert (root / "docs" / "plans").exists()
            assert (root / "docs" / "test-scenarios").exists()

    def test_scaffold_creates_config_toml(self):
        """scaffold_project creates .flowtui/config.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root, project_name="TestApp", stack="Python")

            config_file = root / ".flowtui" / "config.toml"
            assert config_file.exists()

            # Verify content
            content = config_file.read_text()
            assert "TestApp" in content
            assert "Python" in content
            assert "[project]" in content

    def test_scaffold_creates_routing_toml(self):
        """scaffold_project creates .flowtui/routing.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root, project_name="TestApp")

            routing_file = root / ".flowtui" / "routing.toml"
            assert routing_file.exists()

    def test_scaffold_creates_claude_md(self):
        """scaffold_project creates CLAUDE.md in root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root, project_name="TestApp", stack="Python/Textual")

            claude_file = root / "CLAUDE.md"
            assert claude_file.exists()

            # Verify content
            content = claude_file.read_text()
            assert "TestApp" in content
            assert "Python/Textual" in content

    def test_scaffold_creates_agents_md(self):
        """scaffold_project creates AGENTS.md in root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root, project_name="TestApp")

            agents_file = root / "AGENTS.md"
            assert agents_file.exists()

            # Verify content
            content = agents_file.read_text()
            assert "TestApp" in content

    def test_scaffold_uses_default_project_name(self):
        """scaffold_project uses directory name as default project name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "my_project"
            root.mkdir()

            # Don't provide project_name
            scaffold_project(root)

            # Check that directory name was used
            config_file = root / ".flowtui" / "config.toml"
            content = config_file.read_text()
            assert "my_project" in content

    def test_scaffold_uses_default_stack(self):
        """scaffold_project uses 'Python' as default stack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Don't provide stack
            scaffold_project(root, project_name="App")

            config_file = root / ".flowtui" / "config.toml"
            content = config_file.read_text()
            assert "Python" in content

    def test_scaffold_refuses_if_exists(self):
        """scaffold_project raises if .flowtui/ exists and force=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # First scaffold
            scaffold_project(root, project_name="App1")

            # Second scaffold should raise
            with pytest.raises(AlreadyInitializedError):
                scaffold_project(root, project_name="App2", force=False)

    def test_scaffold_force_overwrites(self):
        """scaffold_project with force=True overwrites existing setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # First scaffold
            scaffold_project(root, project_name="App1", stack="Python")
            config1 = (root / ".flowtui" / "config.toml").read_text()
            assert "App1" in config1

            # Second scaffold with force=True
            scaffold_project(root, project_name="App2", stack="Node", force=True)
            config2 = (root / ".flowtui" / "config.toml").read_text()
            assert "App2" in config2
            assert "Node" in config2

    def test_scaffold_preserves_pm_tasks(self):
        """PM/tasks/ directory is preserved during scaffold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # First scaffold
            scaffold_project(root)
            tasks_dir = root / "PM" / "tasks"

            # Create a test file in tasks
            test_file = tasks_dir / "TASK-001.md"
            test_file.write_text("Test task")

            # Scaffold again with force
            scaffold_project(root, force=True)

            # Test file should still exist
            assert test_file.exists()
            assert test_file.read_text() == "Test task"

    def test_scaffold_with_custom_names(self):
        """scaffold_project accepts custom project name and stack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(
                root,
                project_name="MySpecialApp",
                stack="Go/Cobra"
            )

            # Check config
            config_file = root / ".flowtui" / "config.toml"
            content = config_file.read_text()
            assert "MySpecialApp" in content
            assert "Go/Cobra" in content

            # Check CLAUDE.md
            claude_file = root / "CLAUDE.md"
            content = claude_file.read_text()
            assert "MySpecialApp" in content
            assert "Go/Cobra" in content


class TestAlreadyInitializedError:
    """Test AlreadyInitializedError exception."""

    def test_error_is_exception(self):
        """AlreadyInitializedError is an Exception."""
        assert issubclass(AlreadyInitializedError, Exception)

    def test_error_has_message(self):
        """AlreadyInitializedError can be created with a message."""
        error = AlreadyInitializedError("Test message")
        assert str(error) == "Test message"


class TestScaffoldIntegration:
    """Integration tests for scaffolding."""

    def test_scaffold_can_load_config(self):
        """Scaffolded config.toml can be parsed as valid TOML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root, project_name="LoadTest", stack="Python")

            config_file = root / ".flowtui" / "config.toml"
            content = config_file.read_text()

            # Try to parse as TOML
            import tomllib
            config = tomllib.loads(content)

            assert config["project"]["name"] == "LoadTest"
            assert config["project"]["stack"] == "Python"

    def test_scaffold_minimal_init(self):
        """Minimal scaffold call with only root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Call with just root
            scaffold_project(root)

            # Verify basic structure
            assert (root / ".flowtui" / "config.toml").exists()
            assert (root / "PM").exists()
            assert (root / "CLAUDE.md").exists()

    def test_scaffold_creates_empty_directories(self):
        """Scaffold creates empty PM/tasks/ and docs/ subdirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scaffold_project(root)

            # Empty directories should still exist
            assert (root / "PM" / "tasks").is_dir()
            assert list((root / "PM" / "tasks").iterdir()) == []  # empty
            assert (root / "docs" / "context").is_dir()
