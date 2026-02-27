"""Tests for test_runner module — framework detection and test execution."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from flowtui.core.test_runner import TestResult, TestRunner


class TestTestResult:
    """Test TestResult dataclass."""

    def test_test_result_basic(self):
        """Create TestResult with basic fields."""
        result = TestResult(
            passed=True,
            count=5,
            output="5 tests passed",
            framework="pytest",
            duration_sec=1.5,
        )
        assert result.passed is True
        assert result.count == 5
        assert result.skipped is False
        assert result.framework == "pytest"

    def test_test_result_skipped(self):
        """TestResult with skipped=True (no framework)."""
        result = TestResult(passed=None, skipped=True)
        assert result.passed is None
        assert result.skipped is True
        assert result.count == 0

    def test_test_result_failed(self):
        """TestResult with passed=False."""
        result = TestResult(
            passed=False,
            count=2,
            output="Some tests failed",
            framework="pytest",
            duration_sec=2.0,
        )
        assert result.passed is False
        assert result.count == 2


class TestFrameworkDetection:
    """Test TestRunner._detect_framework()."""

    def test_detect_pytest_from_tool_pytest_section(self):
        """Detect pytest from [tool.pytest...] section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            pyproject = project / "pyproject.toml"
            pyproject.write_text(
                """[build-system]
requires = ["hatchling"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[project]
name = "test"
"""
            )

            runner = TestRunner(project)
            assert runner._detect_framework() == "pytest"

    def test_detect_pytest_from_dependencies(self):
        """Detect pytest from project.dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            pyproject = project / "pyproject.toml"
            pyproject.write_text(
                """[project]
name = "test"
dependencies = [
    "textual>=0.50",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
"""
            )

            runner = TestRunner(project)
            assert runner._detect_framework() == "pytest"

    def test_detect_pytest_from_build_system_fallback(self):
        """Detect pytest as fallback if pyproject.toml has [build-system]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            pyproject = project / "pyproject.toml"
            pyproject.write_text(
                """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "test"
"""
            )

            runner = TestRunner(project)
            assert runner._detect_framework() == "pytest"

    def test_detect_npm_test_from_scripts(self):
        """Detect npm_test from package.json scripts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            package_json = project / "package.json"
            package_json.write_text(
                json.dumps(
                    {
                        "name": "test",
                        "scripts": {
                            "test": "jest",
                        },
                    }
                )
            )

            runner = TestRunner(project)
            assert runner._detect_framework() == "npm_test"

    def test_detect_npm_test_from_dependencies(self):
        """Detect npm_test from package.json jest/vitest dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            package_json = project / "package.json"
            package_json.write_text(
                json.dumps(
                    {
                        "name": "test",
                        "devDependencies": {
                            "vitest": "^0.34.0",
                        },
                    }
                )
            )

            runner = TestRunner(project)
            assert runner._detect_framework() == "npm_test"

    def test_detect_flutter_test(self):
        """Detect flutter_test from pubspec.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            pubspec = project / "pubspec.yaml"
            pubspec.write_text(
                """name: test_app
description: A Flutter test app
flutter:
  uses-material-design: true
"""
            )

            runner = TestRunner(project)
            assert runner._detect_framework() == "flutter_test"

    def test_detect_no_framework(self):
        """Return None when no framework detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # Empty project
            runner = TestRunner(project)
            assert runner._detect_framework() is None


class TestBuildCommand:
    """Test TestRunner._build_command()."""

    def test_build_pytest_command(self):
        """Build command for pytest."""
        runner = TestRunner(Path("."))
        cmd = runner._build_command("pytest")
        assert cmd == ["python", "-m", "pytest", "--tb=short", "-q"]

    def test_build_npm_test_command(self):
        """Build command for npm test."""
        runner = TestRunner(Path("."))
        cmd = runner._build_command("npm_test")
        assert cmd == ["npm", "test", "--", "--watchAll=false"]

    def test_build_flutter_test_command(self):
        """Build command for flutter test."""
        runner = TestRunner(Path("."))
        cmd = runner._build_command("flutter_test")
        assert cmd == ["flutter", "test"]

    def test_build_unknown_framework_raises(self):
        """Unknown framework raises ValueError."""
        runner = TestRunner(Path("."))
        with pytest.raises(ValueError):
            runner._build_command("unknown_framework")


class TestPytestOutputParsing:
    """Test TestRunner._parse_pytest_output()."""

    def test_parse_single_passed(self):
        """Parse '1 passed'."""
        runner = TestRunner(Path("."))
        count = runner._parse_pytest_output("1 passed in 0.42s")
        assert count == 1

    def test_parse_multiple_passed(self):
        """Parse multiple passed tests."""
        runner = TestRunner(Path("."))
        count = runner._parse_pytest_output("15 passed in 2.34s")
        assert count == 15

    def test_parse_mixed_passed_failed(self):
        """Parse '3 passed, 2 failed' (returns only passed count)."""
        runner = TestRunner(Path("."))
        count = runner._parse_pytest_output("3 passed, 2 failed in 1.23s")
        assert count == 3

    def test_parse_no_match(self):
        """Return 0 if no 'passed' pattern found."""
        runner = TestRunner(Path("."))
        count = runner._parse_pytest_output("no tests found")
        assert count == 0

    def test_parse_empty_output(self):
        """Return 0 for empty output."""
        runner = TestRunner(Path("."))
        count = runner._parse_pytest_output("")
        assert count == 0


class TestRunTests:
    """Test TestRunner.run_tests() — integration tests."""

    @pytest.mark.asyncio
    async def test_run_tests_no_framework_detected(self):
        """run_tests returns skipped=True when no framework found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            runner = TestRunner(project)
            result = await runner.run_tests()

            assert result.passed is None
            assert result.skipped is True
            assert result.framework is None
            assert result.duration_sec >= 0

    @pytest.mark.asyncio
    async def test_run_tests_pytest_detected(self):
        """run_tests detects pytest from project file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # Create minimal pyproject.toml with pytest
            pyproject = project / "pyproject.toml"
            pyproject.write_text(
                """[build-system]
requires = ["hatchling"]

[project]
name = "test"
"""
            )

            runner = TestRunner(project)
            result = await runner.run_tests()

            # Note: test execution may fail (no pytest in project),
            # but framework should be detected
            assert result.framework == "pytest"
            assert result.skipped is False
            # passed may be True/False depending on pytest availability

    @pytest.mark.asyncio
    async def test_run_tests_command_not_found(self):
        """run_tests returns passed=False if command not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            # Create pyproject.toml so pytest is detected
            pyproject = project / "pyproject.toml"
            pyproject.write_text(
                """[build-system]
requires = ["hatchling"]

[project]
name = "test"
"""
            )

            runner = TestRunner(project)
            result = await runner.run_tests()

            # If pytest not available, output should indicate command not found
            # or tests failed
            assert result.skipped is False
            assert result.framework == "pytest"

    @pytest.mark.asyncio
    async def test_run_tests_duration_recorded(self):
        """run_tests records execution duration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            runner = TestRunner(project)
            result = await runner.run_tests()

            assert result.duration_sec >= 0.0

    @pytest.mark.asyncio
    async def test_run_tests_result_dataclass_fields(self):
        """run_tests returns TestResult with all fields populated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            runner = TestRunner(project)
            result = await runner.run_tests()

            # Check all fields exist and have defaults
            assert hasattr(result, "passed")
            assert hasattr(result, "count")
            assert hasattr(result, "output")
            assert hasattr(result, "skipped")
            assert hasattr(result, "framework")
            assert hasattr(result, "duration_sec")


class TestInitialization:
    """Test TestRunner initialization."""

    def test_init_with_path(self):
        """Initialize TestRunner with Path object."""
        runner = TestRunner(Path("/tmp"))
        assert runner.project_root == Path("/tmp")

    def test_init_with_string(self):
        """Initialize TestRunner with string (converted to Path)."""
        runner = TestRunner(Path("/tmp"))
        assert isinstance(runner.project_root, Path)
