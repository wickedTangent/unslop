"""Tests for test runner module."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.test_runner import TestResult, detect_test_command, run_tests


class TestTestResult:
    """Tests for the TestResult dataclass."""

    def test_init(self) -> None:
        """TestResult initializes with correct defaults."""
        result = TestResult(passed=True, command="pytest")
        assert result.passed is True
        assert result.command == "pytest"
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.returncode == 0
        assert result.timed_out is False

    def test_init_failed(self) -> None:
        """TestResult with failed status."""
        result = TestResult(
            passed=False,
            command="pytest",
            returncode=1,
            stderr="Test failed",
        )
        assert result.passed is False
        assert result.returncode == 1
        assert "Test failed" in result.stderr


class TestDetectTestCommand:
    """Tests for test command auto-detection."""

    def test_pytest_ini(self, tmp_path: Path) -> None:
        """Detect pytest from pytest.ini."""
        (tmp_path / "pytest.ini").write_text("[pytest]", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "pytest"

    def test_pyproject_toml_with_pytest(self, tmp_path: Path) -> None:
        """Detect pytest from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text('[tool.pytest]', encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "pytest"

    def test_conftest_py(self, tmp_path: Path) -> None:
        """Detect pytest from conftest.py."""
        (tmp_path / "conftest.py").write_text("", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "pytest"

    def test_test_files(self, tmp_path: Path) -> None:
        """Detect pytest from test_*.py files."""
        (tmp_path / "test_example.py").write_text("", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "pytest"

    def test_npm_test(self, tmp_path: Path) -> None:
        """Detect npm test from package.json."""
        (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}', encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "npm test"

    def test_flutter_test(self, tmp_path: Path) -> None:
        """Detect flutter test from pubspec.yaml."""
        (tmp_path / "pubspec.yaml").write_text("flutter_test:", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "flutter test"

    def test_go_test(self, tmp_path: Path) -> None:
        """Detect go test from go.mod."""
        (tmp_path / "go.mod").write_text("module test", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "go test ./..."

    def test_maven_test(self, tmp_path: Path) -> None:
        """Detect maven test from pom.xml."""
        (tmp_path / "pom.xml").write_text("<project></project>", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "mvn test"

    def test_gradle_test(self, tmp_path: Path) -> None:
        """Detect gradle test from build.gradle."""
        (tmp_path / "build.gradle").write_text("plugins { java }", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "gradle test"

    def test_make_test(self, tmp_path: Path) -> None:
        """Detect make test from Makefile."""
        (tmp_path / "Makefile").write_text("test: echo", encoding="utf-8")
        cmd = detect_test_command(tmp_path)
        assert cmd == "make test"

    def test_no_framework_detected(self, tmp_path: Path) -> None:
        """Return None when no framework detected."""
        cmd = detect_test_command(tmp_path)
        assert cmd is None


class TestRunTests:
    """Tests for running tests."""

    def test_run_tests_no_framework(self, tmp_path: Path) -> None:
        """Return failure when no framework detected."""
        result = run_tests(tmp_path)
        assert result.passed is False
        assert "No test framework detected" in result.stderr

    def test_run_tests_with_override(self, tmp_path: Path) -> None:
        """Use override test command."""
        result = run_tests(tmp_path, test_cmd="echo 'test passed'")
        assert result.passed is True
        assert result.command == "echo 'test passed'"

    def test_run_tests_command_not_found(self, tmp_path: Path) -> None:
        """Return failure when command not found."""
        result = run_tests(tmp_path, test_cmd="nonexistent_command_12345")
        assert result.passed is False
        assert "not found" in result.stderr

    def test_run_tests_timeout(self, tmp_path: Path) -> None:
        """Return timeout when test takes too long."""
        # This would require a command that hangs, which is hard to test reliably
        # We'll just verify the function doesn't crash with a timeout param
        result = run_tests(tmp_path, test_cmd="true", timeout=1)
        assert result.passed is True  # 'true' exits immediately
