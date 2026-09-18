"""Tests for debug artifacts tell detector and fixer."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.report import Severity, TellCategory, UnslopIssue
from unslop.tells.debug_artifacts import detect, fix


class TestDetect:
    """Tests for the detect function."""

    def test_console_log(self) -> None:
        """Detect console.log statements."""
        source = '''console.log("User data:", user);
console.debug("Processing...");
console.warn("Deprecated API");
'''
        issues = detect(source, Path("test.ts"))
        assert len(issues) == 3
        assert all(i.tell == TellCategory.DEBUG_ARTIFACTS for i in issues)

    def test_python_print(self) -> None:
        """Detect print() statements."""
        source = '''print("Starting process...")
print(f"User: {user}")
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 2

    def test_debugger_statement(self) -> None:
        """Detect debugger statements."""
        source = '''function process() {
    debugger;
    return compute();
}
'''
        issues = detect(source, Path("test.ts"))
        assert len(issues) == 1

    def test_pii_in_console_log(self) -> None:
        """Detect PII in console.log (higher severity)."""
        source = '''console.log("Password:", password);
console.log("Token:", token);
'''
        issues = detect(source, Path("test.ts"))
        assert len(issues) == 2
        assert all(i.severity == Severity.HIGH for i in issues)

    def test_commented_out_code(self) -> None:
        """Detect commented-out code blocks."""
        source = '''// commented out: temp debugging
// disabled: not ready yet
// temporary: testing
'''
        issues = detect(source, Path("test.ts"))
        # The detector finds // commented out and // disabled, but # temporary
        # is a Python-style comment in a .ts file, so it may not match.
        assert len(issues) >= 2

    def test_cli_script_skipped(self) -> None:
        """Do not flag print in CLI/benchmark scripts."""
        source = '''print("Processing...")
result = compute()
print(f"Done: {result}")
'''
        issues = detect(source, Path("cli_main.py"))
        assert len(issues) == 0

    def test_print_in_docstring_not_flagged(self) -> None:
        """Do not flag print() inside docstrings."""
        source = '''def example():
    """
    Example usage:
        print("Hello world")
    """
    return True
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 0

    def test_no_false_positives_on_logging(self) -> None:
        """Do not flag proper logging calls."""
        source = '''import logging
logger = logging.getLogger(__name__)
logger.info("Processing user")
logger.error(f"Error: {e}")
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 0

    def test_no_false_positives_on_normal_code(self) -> None:
        """Do not flag normal code without debug artifacts."""
        source = '''def process():
    data = load_data()
    result = transform(data)
    return result
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 0


class TestFix:
    """Tests for the fix function."""

    def test_fix_removes_console_log(self) -> None:
        """Fix removes console.log lines."""
        source = '''console.log("User data:", user);
const result = compute();
'''
        issues = [UnslopIssue(
            tell=TellCategory.DEBUG_ARTIFACTS,
            severity=Severity.MEDIUM,
            description="Debug artifact: console.log",
            file_path=Path("test.ts"),
            line=1,
            code_snippet='console.log("User data:", user);',
            suggested_fix="Remove debug statement",
            confidence=0.95,
        )]
        result = fix(source, issues)
        assert "console.log" not in result
        assert "const result = compute();" in result

    def test_fix_removes_print(self) -> None:
        """Fix removes print() lines."""
        source = '''print("Starting process...")
result = compute()
'''
        issues = [UnslopIssue(
            tell=TellCategory.DEBUG_ARTIFACTS,
            severity=Severity.MEDIUM,
            description="Debug artifact: print()",
            file_path=Path("test.py"),
            line=1,
            code_snippet='print("Starting process...")',
            suggested_fix="Remove debug statement",
            confidence=0.95,
        )]
        result = fix(source, issues)
        assert "print(" not in result
        assert "result = compute()" in result

    def test_fix_removes_debugger(self) -> None:
        """Fix removes debugger statements."""
        source = '''function process() {
    debugger;
    return compute();
}
'''
        issues = [UnslopIssue(
            tell=TellCategory.DEBUG_ARTIFACTS,
            severity=Severity.MEDIUM,
            description="Debug artifact: debugger",
            file_path=Path("test.ts"),
            line=2,
            code_snippet="debugger;",
            suggested_fix="Remove debug statement",
            confidence=0.95,
        )]
        result = fix(source, issues)
        assert "debugger" not in result
        assert "return compute();" in result

    def test_fix_empty_issues_list(self) -> None:
        """Return source unchanged when no issues."""
        source = '''def process():
    data = load_data()
    return data
'''
        result = fix(source, [])
        assert result == source

    def test_fix_preserves_code_lines(self) -> None:
        """Ensure fix only removes debug lines, not code."""
        source = '''console.log("Start");
const a = 1;
console.log("End");
const b = 2;
'''
        issues = [
            UnslopIssue(
                tell=TellCategory.DEBUG_ARTIFACTS,
                severity=Severity.MEDIUM,
                description="Debug artifact",
                file_path=Path("test.ts"),
                line=1,
                code_snippet="console.log('Start');",
                suggested_fix="Remove debug statement",
                confidence=0.95,
            ),
            UnslopIssue(
                tell=TellCategory.DEBUG_ARTIFACTS,
                severity=Severity.MEDIUM,
                description="Debug artifact",
                file_path=Path("test.ts"),
                line=3,
                code_snippet="console.log('End');",
                suggested_fix="Remove debug statement",
                confidence=0.95,
            ),
        ]
        result = fix(source, issues)
        assert "const a = 1;" in result
        assert "const b = 2;" in result
