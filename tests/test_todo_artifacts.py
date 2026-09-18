"""Tests for TODO artifacts tell detector and fixer."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.report import Severity, TellCategory, UnslopIssue
from unslop.tells.todo_artifacts import detect, fix


class TestDetect:
    """Tests for the detect function."""

    def test_todo_comment(self) -> None:
        """Detect TODO comments."""
        source = '''# TODO: add real authentication here
def authenticate(user, password):
    return True
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 1
        assert issues[0].tell == TellCategory.TODO_ARTIFACTS
        assert issues[0].severity == Severity.MEDIUM
        assert issues[0].line == 1

    def test_fixme_comment(self) -> None:
        """Detect FIXME comments (higher severity)."""
        source = '''// FIXME: this is broken
def process():
    pass
'''
        issues = detect(source, Path("test.ts"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH

    def test_hack_comment(self) -> None:
        """Detect HACK comments."""
        source = '''# HACK: temporary workaround
result = force_compute(data)
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_xxx_comment(self) -> None:
        """Detect XXX comments."""
        source = '''// XXX: needs review
def validate(user):
    return True
'''
        issues = detect(source, Path("test.ts"))
        assert len(issues) == 1

    def test_bug_comment(self) -> None:
        """Detect BUG comments (higher severity)."""
        source = '''# BUG: this fails on empty input
def process(data):
    return data[0]
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH

    def test_workaround_comment(self) -> None:
        """Detect WORKAROUND comments."""
        source = '''// WORKAROUND: server doesn't support pagination
all_items = fetch_all()
'''
        issues = detect(source, Path("test.ts"))
        assert len(issues) == 1

    def test_case_insensitive(self) -> None:
        """Detect TODO in any case."""
        source = '''# todo: lowercase
# Todo: mixed case
# TODO: uppercase
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 3

    def test_multiple_on_same_file(self) -> None:
        """Detect multiple TODOs in a file."""
        source = '''# TODO: add validation
def validate(data):
    pass

# FIXME: handle edge case
def process(data):
    return data

# HACK: workaround
def compute():
    return 42
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 3

    def test_no_false_positives_on_normal_code(self) -> None:
        """Do not flag normal code without TODOs."""
        source = '''def process():
    data = load_data()
    result = transform(data)
    return result
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 0


class TestFix:
    """Tests for the fix function."""

    def test_fix_removes_standalone_todo_lines(self) -> None:
        """Fix removes standalone TODO comment lines."""
        source = '''# TODO: add real authentication here
def authenticate(user, password):
    return True
'''
        issues = [UnslopIssue(
            tell=TellCategory.TODO_ARTIFACTS,
            severity=Severity.MEDIUM,
            description="TODO in production code",
            file_path=Path("test.py"),
            line=1,
            code_snippet="# TODO: add real authentication here",
            suggested_fix="Remove TODO comment",
            confidence=0.95,
        )]
        result = fix(source, issues)
        assert "# TODO:" not in result
        assert "def authenticate" in result

    def test_fix_preserves_code_with_inline_todo(self) -> None:
        """Fix does not remove code that has inline TODO."""
        source = '''result = compute(data)  # TODO: optimize later
return result
'''
        issues = [UnslopIssue(
            tell=TellCategory.TODO_ARTIFACTS,
            severity=Severity.MEDIUM,
            description="TODO in production code",
            file_path=Path("test.py"),
            line=1,
            code_snippet="result = compute(data)  # TODO: optimize later",
            suggested_fix="Remove TODO comment",
            confidence=0.95,
        )]
        result = fix(source, issues)
        # Code line should be preserved (not a standalone comment)
        assert "result = compute(data)" in result

    def test_fix_empty_issues_list(self) -> None:
        """Return source unchanged when no issues."""
        source = '''def process():
    data = load_data()
    return data
'''
        result = fix(source, [])
        assert result == source

    def test_fix_preserves_code_lines(self) -> None:
        """Ensure fix only removes comment lines, not code."""
        source = '''# TODO: add validation
def validate(data):
    return is_valid(data)

# FIXME: handle edge case
def process(data):
    return transform(data)
'''
        issues = [
            UnslopIssue(
                tell=TellCategory.TODO_ARTIFACTS,
                severity=Severity.MEDIUM,
                description="TODO in production code",
                file_path=Path("test.py"),
                line=1,
                code_snippet="# TODO: add validation",
                suggested_fix="Remove TODO comment",
                confidence=0.95,
            ),
            UnslopIssue(
                tell=TellCategory.TODO_ARTIFACTS,
                severity=Severity.HIGH,
                description="FIXME in production code",
                file_path=Path("test.py"),
                line=6,
                code_snippet="# FIXME: handle edge case",
                suggested_fix="Remove FIXME comment",
                confidence=0.95,
            ),
        ]
        result = fix(source, issues)
        # Code lines should be preserved
        assert "def validate" in result
        assert "return is_valid(data)" in result
        assert "def process" in result
        assert "return transform(data)" in result
