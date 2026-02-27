"""Test framework detection and runner — auto-detect pytest/npm/flutter."""

import asyncio
import os
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    """Result of test execution."""

    passed: bool | None  # None if skipped (no framework detected)
    count: int = 0  # Number of tests (0 if unknown)
    output: str = ""  # Raw test output
    skipped: bool = False  # True if no framework found
    framework: str | None = None  # Framework used (pytest, npm_test, flutter_test)
    duration_sec: float = 0.0  # Execution duration


class TestRunner:
    """Auto-detect test framework and run tests."""

    def __init__(self, project_root: Path):
        """Initialize test runner for given project root.

        Args:
            project_root: Root directory of project to run tests in.
        """
        self.project_root = Path(project_root)

    def _detect_framework(self) -> str | None:
        """Auto-detect test framework from project files.

        Checks in order:
        1. pyproject.toml: pytest config or pytest in dependencies
        2. package.json: npm test script or jest/vitest
        3. pubspec.yaml: flutter/dart test support

        Returns:
            "pytest" | "npm_test" | "flutter_test" | None
        """
        # Check pyproject.toml for Python/pytest
        pyproject_path = self.project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                content = pyproject_path.read_text(encoding="utf-8")
                config = tomllib.loads(content)

                # Check for [tool.pytest...] section
                if "tool" in config and "pytest" in config["tool"]:
                    return "pytest"

                # Check dependencies for pytest
                if "project" in config:
                    deps = config["project"].get("dependencies", [])
                    opt_deps = config["project"].get("optional-dependencies", {})
                    all_deps = deps + opt_deps.get("dev", [])

                    for dep in all_deps:
                        # Match "pytest>=7.0" or "pytest"
                        if re.match(r"pytest(?:>=|<=|==|!=|>|<|\[)?", dep):
                            return "pytest"

                # Fallback: if pyproject.toml has [build-system], assume Python project
                if "build-system" in config:
                    return "pytest"

            except Exception:
                # Failed to parse pyproject.toml, continue to next check
                pass

        # Check package.json for npm/Node tests
        package_json_path = self.project_root / "package.json"
        if package_json_path.exists():
            try:
                import json

                content = package_json_path.read_text(encoding="utf-8")
                config = json.loads(content)

                # Check for test script
                if "scripts" in config and "test" in config["scripts"]:
                    return "npm_test"

                # Check for jest/vitest in dependencies
                deps = config.get("dependencies", {})
                dev_deps = config.get("devDependencies", {})
                all_deps = list(deps.keys()) + list(dev_deps.keys())

                for dep in all_deps:
                    if dep in ("jest", "vitest"):
                        return "npm_test"

            except Exception:
                # Failed to parse package.json, continue to next check
                pass

        # Check pubspec.yaml for Flutter/Dart tests
        pubspec_path = self.project_root / "pubspec.yaml"
        if pubspec_path.exists():
            try:
                content = pubspec_path.read_text(encoding="utf-8")
                # Simple check: if pubspec.yaml exists and contains "flutter" it's Flutter
                if "flutter" in content.lower():
                    return "flutter_test"
                # Otherwise it's a Dart project
                return "flutter_test"

            except Exception:
                # Failed to parse pubspec.yaml
                pass

        return None

    def _build_command(self, framework: str) -> list[str]:
        """Build test command for framework.

        Args:
            framework: Framework name from _detect_framework()

        Returns:
            Command list for asyncio.create_subprocess_exec()
        """
        if framework == "pytest":
            return ["python", "-m", "pytest", "--tb=short", "-q"]
        elif framework == "npm_test":
            return ["npm", "test", "--", "--watchAll=false"]
        elif framework == "flutter_test":
            return ["flutter", "test"]
        else:
            raise ValueError(f"Unknown framework: {framework}")

    def _parse_pytest_output(self, output: str) -> int:
        """Parse pytest output to extract test count.

        Looks for patterns like:
        - "5 passed in 1.23s"
        - "3 passed, 2 failed"
        - "1 passed"

        Args:
            output: Raw pytest output

        Returns:
            Number of tests passed, or 0 if not found
        """
        # Match "X passed" pattern
        match = re.search(r"(\d+)\s+passed", output)
        if match:
            return int(match.group(1))
        return 0

    async def run_tests(self) -> TestResult:
        """Detect framework and run tests.

        If no framework detected, returns TestResult(passed=None, skipped=True).
        If framework found, runs tests and parses output.
        Timeout: 300 seconds.

        Returns:
            TestResult with status, count, output, and framework info.
        """
        start_time = time.monotonic()

        # Auto-detect framework
        framework = self._detect_framework()
        if framework is None:
            duration = time.monotonic() - start_time
            return TestResult(
                passed=None,
                count=0,
                output="",
                skipped=True,
                framework=None,
                duration_sec=duration,
            )

        # Build command
        cmd = self._build_command(framework)

        try:
            # Strip CLAUDECODE to allow nested invocations
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

            # Create subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
                env=env,
            )

            try:
                # Wait for process with timeout
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=300.0
                )
            except asyncio.TimeoutError:
                # Kill process on timeout
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()

                duration = time.monotonic() - start_time
                return TestResult(
                    passed=False,
                    count=0,
                    output="Tests timed out after 300s",
                    skipped=False,
                    framework=framework,
                    duration_sec=duration,
                )

            duration = time.monotonic() - start_time
            output = stdout_data.decode("utf-8", errors="replace")
            stderr_output = stderr_data.decode("utf-8", errors="replace")

            # Combine stdout + stderr for parsing
            full_output = output + "\n" + stderr_output if stderr_output else output

            # Determine pass/fail based on returncode
            passed = proc.returncode == 0

            # Parse test count
            count = 0
            if framework == "pytest":
                count = self._parse_pytest_output(full_output)

            return TestResult(
                passed=passed,
                count=count,
                output=output,
                skipped=False,
                framework=framework,
                duration_sec=duration,
            )

        except FileNotFoundError as e:
            duration = time.monotonic() - start_time
            return TestResult(
                passed=False,
                count=0,
                output=f"Framework command not found: {cmd[0]}",
                skipped=False,
                framework=framework,
                duration_sec=duration,
            )
        except Exception as e:
            duration = time.monotonic() - start_time
            return TestResult(
                passed=False,
                count=0,
                output=f"Error running tests: {str(e)}",
                skipped=False,
                framework=framework,
                duration_sec=duration,
            )
