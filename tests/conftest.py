"""Shared pytest fixtures for FlowTUI tests."""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from flowtui.core.invoker import MockCLI
from flowtui.config import FlowTUIConfig, ProjectConfig, LimitsConfig


@pytest.fixture
def mock_cli():
    """MockCLI fixture with default pass response."""
    cli = MockCLI(responses={"cc": "## Review Result: PASS\n5 passed"})
    return cli


@pytest.fixture
def mock_cli_with_responses():
    """MockCLI factory fixture for custom responses."""
    def _make_cli(responses: dict[str, str], delay: float = 0.0) -> MockCLI:
        return MockCLI(responses=responses, delay=delay)
    return _make_cli


@pytest.fixture
def tmp_project():
    """
    Temporary project root with minimal FlowTUI structure:
    - .flowtui/config.toml (valid minimal config)
    - docs/tasks/ directory
    - git repo initialized
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Clean environment: strip CLAUDECODE to avoid nested CC interference
        _clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=root,
            check=True,
            capture_output=True,
            env=_clean_env,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=root,
            check=True,
            capture_output=True,
            env=_clean_env,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=root,
            check=True,
            capture_output=True,
            env=_clean_env,
        )

        # Create initial commit
        (root / "README.md").write_text("# Test Project\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=root,
            check=True,
            capture_output=True,
            env=_clean_env,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=root,
            check=True,
            capture_output=True,
            env=_clean_env,
        )

        # Create .flowtui/config.toml
        flowtui_dir = root / ".flowtui"
        flowtui_dir.mkdir()

        config_content = """
[project]
name = "test-project"
stack = "Python 3.11"
description = "Test Project"

[limits]
claude_daily_budget = 50
codex_daily_budget = 5
gemini_daily_budget = 100

[startup]
auto_update = false
"""
        (flowtui_dir / "config.toml").write_text(config_content)

        # Create docs/tasks directory
        (root / "docs" / "tasks").mkdir(parents=True)

        yield root


@pytest.fixture
def flowtui_config_obj():
    """Minimal FlowTUIConfig for testing."""
    return FlowTUIConfig(
        project=ProjectConfig(
            name="test-project",
            stack="Python 3.11",
            description="Test Project",
        ),
        limits=LimitsConfig(
            claude_daily_budget=50,
            codex_daily_budget=5,
            gemini_daily_budget=100,
        ),
    )


@pytest.fixture
def temp_project_dir():
    """Temporary project directory with docs/tasks structure (legacy alias)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "docs").mkdir(exist_ok=True)
        (path / "docs" / "tasks").mkdir(exist_ok=True)
        yield path


@pytest.fixture
def mock_config():
    """Mock FlowTUIConfig with basic attributes."""
    # Minimal mock for compatibility with existing tests
    config = type("MockConfig", (), {
        "project": type("Project", (), {
            "name": "TestProject",
            "stack": "Python 3.11 + Textual",
        })(),
    })()
    return config
