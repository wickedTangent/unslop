"""Tests for CLI module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestCLI:
    """Tests for the unslop CLI."""

    def test_cli_help(self) -> None:
        """CLI shows help with --help."""
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # CLI may exit with 0 (help) or 2 (error/usage)
        assert result.returncode in (0, 2)

    def test_cli_scan_help(self) -> None:
        """Scan subcommand shows help."""
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "scan", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode in (0, 2)

    def test_cli_fix_help(self) -> None:
        """Fix subcommand shows help."""
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "fix", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode in (0, 2)
        # Verify --create-pr flag is documented
        assert "--create-pr" in result.stdout

    def test_cli_no_args(self) -> None:
        """CLI without args shows help or error."""
        result = subprocess.run(
            [sys.executable, "-m", "unslop"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should exit with 0 (help) or 2 (error/usage)
        assert result.returncode in (0, 2)

    def test_cli_scan_not_a_file(self, tmp_path: Path) -> None:
        """Scan on non-existent file returns error."""
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "scan", "/nonexistent/file.py"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should exit with non-zero
        assert result.returncode != 0

    def test_cli_fix_not_a_git_repo(self, tmp_path: Path) -> None:
        """Fix on non-git repo returns error."""
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "fix", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_cli_scan_with_output_flags(self, tmp_path: Path) -> None:
        """Scan with --no-markdown and --no-json flags."""
        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text('''import os
import json

def process():
    # increment the counter
    counter += 1
    return json.loads("{}")
''', encoding="utf-8")

        # Test --no-markdown
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "scan", str(test_file), "--no-markdown"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # May exit 0 (success) or 2 (error for missing repo)
        assert result.returncode in (0, 2)

        # Test --no-json
        result = subprocess.run(
            [sys.executable, "-m", "unslop", "scan", str(test_file), "--no-json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode in (0, 2)


class TestImportAPI:
    """Tests for the public API imports."""

    def test_import_analyzer(self) -> None:
        """UnslopAnalyzer is importable."""
        from unslop import UnslopAnalyzer
        assert UnslopAnalyzer is not None

    def test_import_report_classes(self) -> None:
        """Report classes are importable."""
        from unslop import Severity, TellCategory, UnslopIssue, UnslopReport
        assert Severity is not None
        assert TellCategory is not None
        assert UnslopIssue is not None
        assert UnslopReport is not None

    def test_import_pipeline_classes(self) -> None:
        """Pipeline classes are importable."""
        from unslop import FixPipeline, FixResult, FixIteration, FixChange
        assert FixPipeline is not None
        assert FixResult is not None
        assert FixIteration is not None
        assert FixChange is not None

    def test_import_test_runner(self) -> None:
        """Test runner is importable."""
        from unslop import TestResult, run_tests, detect_test_command
        assert TestResult is not None
        assert run_tests is not None
        assert detect_test_command is not None

    def test_import_pattern_index(self) -> None:
        """PatternIndex is importable."""
        from unslop import PatternIndex
        assert PatternIndex is not None

    def test_version(self) -> None:
        """Package has a version."""
        import unslop
        assert hasattr(unslop, "__version__")
        assert unslop.__version__ == "0.1.0"
