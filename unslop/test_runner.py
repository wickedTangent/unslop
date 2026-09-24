"""Auto-detect and run test commands for unslop fix pipeline.

Detects the test framework from project structure and runs the appropriate
test command with a configurable timeout.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TestResult:
    """Result of running the test suite."""
    passed: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False


def detect_test_command(repo_root: Path) -> Optional[str]:
    """Auto-detect the test command based on project structure.

    Checks for common test framework indicators in priority order:
    1. pytest (pytest.ini, pyproject.toml, conftest.py)
    2. npm test scripts
    3. Jest config
    4. Flutter test
    5. Go test
    6. Maven/Gradle
    7. Make test

    Args:
        repo_root: Path to repository root.

    Returns:
        Test command string, or None if no framework detected.
    """
    # Python / pytest
    if (repo_root / "pytest.ini").exists():
        return "pytest"
    if (repo_root / "pyproject.toml").exists():
        content = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        if "pytest" in content:
            return "pytest"
    if (repo_root / "conftest.py").exists():
        return "pytest"
    if list(repo_root.glob("tests/**/*.py")) or list(repo_root.glob("test_*.py")):
        return "pytest"

    # JavaScript / npm
    pkg_json = repo_root / "package.json"
    if pkg_json.exists():
        content = pkg_json.read_text(encoding="utf-8")
        if '"test"' in content:
            return "npm test"
        if "jest" in content:
            return "npx jest"

    # Flutter
    if (repo_root / "pubspec.yaml").exists():
        content = (repo_root / "pubspec.yaml").read_text(encoding="utf-8")
        if "flutter_test" in content:
            return "flutter test"

    # Go
    if (repo_root / "go.mod").exists():
        return "go test ./..."

    # Java / Maven
    if (repo_root / "pom.xml").exists():
        return "mvn test"

    # Java / Gradle
    if (repo_root / "build.gradle").exists() or (repo_root / "build.gradle.kts").exists():
        return "gradle test"

    # Make
    if (repo_root / "Makefile").exists():
        return "make test"

    return None


def run_tests(
    repo_root: Path,
    test_cmd: Optional[str] = None,
    timeout: int = 120,
) -> TestResult:
    """Run the test suite in the repository.

    Args:
        repo_root: Path to repository root.
        test_cmd: Override test command. Auto-detected if None.
        timeout: Maximum seconds to wait for tests.

    Returns:
        TestResult with pass/fail status.
    """
    if test_cmd is None:
        test_cmd = detect_test_command(repo_root)
        if test_cmd is None:
            return TestResult(
                passed=False,
                command="",
                stderr="No test framework detected. Use --test-cmd to specify a command.",
            )

    if not test_cmd.strip():
        return TestResult(
            passed=False,
            command=test_cmd,
            stderr="No test command specified. Use --test-cmd to specify a command.",
        )

    try:
        command_args = shlex.split(test_cmd)
    except ValueError as exc:
        return TestResult(
            passed=False,
            command=test_cmd,
            stderr=f"Invalid test command: {exc}",
        )

    if not command_args:
        return TestResult(
            passed=False,
            command=test_cmd,
            stderr="No test command specified. Use --test-cmd to specify a command.",
        )

    env = os.environ.copy()
    env["CI"] = "1"  # Ensure CI-friendly output (no colors, etc.)

    try:
        result = subprocess.run(
            command_args,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            shell=False,
        )
        return TestResult(
            passed=result.returncode == 0,
            command=test_cmd,
            stdout=result.stdout[:5000],  # Cap output for report
            stderr=result.stderr[:5000],
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            command=test_cmd,
            stderr=f"Test command timed out after {timeout}s",
            timed_out=True,
        )
    except FileNotFoundError:
        return TestResult(
            passed=False,
            command=test_cmd,
            stderr=f"Test command not found: {test_cmd}",
        )
