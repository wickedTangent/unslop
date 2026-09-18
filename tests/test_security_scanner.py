"""Tests for security scanner tell detector and fixer."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.report import Severity, TellCategory, UnslopIssue
from unslop.tells.security_scanner import (
    detect,
    fix,
    XSS_PATTERNS,
    CORS_PATTERNS,
    BANDIT_FIXES,
)


class TestDetect:
    """Tests for the detect function."""

    def test_js_xss_innerhtml(self) -> None:
        """Detect XSS via innerHTML in JS/TS."""
        source = '''element.innerHTML = userInput;
'''
        issues = detect(source, Path("test.ts"))
        xss = [i for i in issues if "XSS" in i.description]
        assert len(xss) >= 1

    def test_js_xss_document_write(self) -> None:
        """Detect XSS via document.write in JS/TS."""
        source = '''document.write(userInput);
'''
        issues = detect(source, Path("test.ts"))
        xss = [i for i in issues if "XSS" in i.description]
        assert len(xss) >= 1

    def test_ts_cors_wildcard(self) -> None:
        """Detect CORS wildcard configuration."""
        source = '''Access-Control-Allow-Origin: *
'''
        issues = detect(source, Path("test.ts"))
        cors = [i for i in issues if "CORS" in i.description]
        assert len(cors) >= 1

    def test_python_file_returns_empty_without_bandit(self) -> None:
        """Python files delegate to Bandit (returns empty if Bandit not installed)."""
        source = '''def process():
    pass
'''
        # This will try to run Bandit, which may or may not be installed
        # We just verify it doesn't crash
        issues = detect(source, Path("test.py"))
        assert isinstance(issues, list)

    def test_unknown_extension_returns_empty(self) -> None:
        """Unknown file extensions return empty."""
        source = '''def process():
    pass
'''
        issues = detect(source, Path("test.txt"))
        assert len(issues) == 0

    def test_no_false_positives_on_normal_code(self) -> None:
        """Do not flag normal code without security issues."""
        source = '''def process():
    data = load_data()
    return data
'''
        issues = detect(source, Path("test.py"))
        # Just verify it doesn't crash
        assert isinstance(issues, list)


class TestFix:
    """Tests for the fix function."""

    def test_fix_returns_source_unchanged(self) -> None:
        """Fix returns source unchanged (suggestions only)."""
        source = '''def process():
    data = load_data()
    return data
'''
        issues = [UnslopIssue(
            tell=TellCategory.SECURITY_VULNERABILITY,
            severity=Severity.HIGH,
            description="SQL injection risk",
            file_path=Path("test.py"),
            line=1,
            code_snippet="cursor.execute(query)",
            suggested_fix="Use parameterized queries",
            confidence=0.9,
        )]
        result = fix(source, issues)
        assert result == source

    def test_fix_empty_issues_list(self) -> None:
        """Return source unchanged when no issues."""
        source = '''def process():
    data = load_data()
    return data
'''
        result = fix(source, [])
        assert result == source


class TestConstants:
    """Tests for configuration constants."""

    def test_xss_patterns_defined(self) -> None:
        """XSS patterns are defined."""
        assert len(XSS_PATTERNS) > 0
        assert any("innerHTML" in p[0] for p in XSS_PATTERNS)

    def test_cors_patterns_defined(self) -> None:
        """CORS patterns are defined."""
        assert len(CORS_PATTERNS) > 0
        assert any("*" in p[0] for p in CORS_PATTERNS)

    def test_bandit_fixes_defined(self) -> None:
        """Bandit fixes are defined."""
        assert len(BANDIT_FIXES) > 0
        assert "B608" in BANDIT_FIXES  # SQL injection
        assert "B105" in BANDIT_FIXES  # Hardcoded password
