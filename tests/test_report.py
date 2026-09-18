"""Tests for report generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.report import Severity, TellCategory, UnslopIssue, UnslopReport


class TestUnslopReport:
    """Tests for the UnslopReport class."""

    def test_empty_report(self) -> None:
        """Empty report has no issues and score 0."""
        report = UnslopReport()
        assert len(report.issues) == 0
        assert report.slop_score == 0.0

    def test_add_issue(self) -> None:
        """Adding an issue increases the issue count."""
        report = UnslopReport()
        report.add_issue(UnslopIssue(
            tell=TellCategory.VERBOSE_COMMENTS,
            severity=Severity.LOW,
            description="Test issue",
            file_path=Path("test.py"),
            line=1,
            confidence=0.9,
        ))
        assert len(report.issues) == 1

    def test_severity_counts(self) -> None:
        """Severity counts correctly tallies issues."""
        report = UnslopReport()
        report.add_issue(UnslopIssue(
            tell=TellCategory.VERBOSE_COMMENTS,
            severity=Severity.LOW,
            description="Low issue",
            file_path=Path("test.py"),
        ))
        report.add_issue(UnslopIssue(
            tell=TellCategory.EMPTY_ERROR_HANDLING,
            severity=Severity.CRITICAL,
            description="Critical issue",
            file_path=Path("test.py"),
        ))
        report.add_issue(UnslopIssue(
            tell=TellCategory.DEAD_CODE,
            severity=Severity.HIGH,
            description="High issue",
            file_path=Path("test.py"),
        ))

        counts = report.severity_counts()
        assert counts[Severity.LOW] == 1
        assert counts[Severity.CRITICAL] == 1
        assert counts[Severity.HIGH] == 1
        assert counts[Severity.MEDIUM] == 0

    def test_summary_empty(self) -> None:
        """Summary of empty report shows no issues."""
        report = UnslopReport()
        summary = report.summary()
        assert "No issues found" in summary
        assert "0/100" in summary

    def test_summary_with_issues(self) -> None:
        """Summary with issues shows count and breakdown."""
        report = UnslopReport()
        report.add_issue(UnslopIssue(
            tell=TellCategory.VERBOSE_COMMENTS,
            severity=Severity.LOW,
            description="Test issue",
            file_path=Path("test.py"),
        ))
        report.add_issue(UnslopIssue(
            tell=TellCategory.VERBOSE_COMMENTS,
            severity=Severity.LOW,
            description="Test issue 2",
            file_path=Path("test.py"),
        ))
        report.add_issue(UnslopIssue(
            tell=TellCategory.EMPTY_ERROR_HANDLING,
            severity=Severity.CRITICAL,
            description="Critical issue",
            file_path=Path("test.py"),
        ))

        summary = report.summary()
        assert "3" in summary  # Total issues
        assert "verbose_comments" in summary
        assert "empty_error_handling" in summary

    def test_to_markdown_empty(self) -> None:
        """Markdown of empty report shows clean status."""
        report = UnslopReport()
        md = report.to_markdown()
        assert "# Unslop Report" in md
        assert "0/100" in md
        assert "Clean" in md

    def test_to_markdown_with_issues(self) -> None:
        """Markdown with issues shows severity breakdown and details."""
        report = UnslopReport()
        report.add_issue(UnslopIssue(
            tell=TellCategory.EMPTY_ERROR_HANDLING,
            severity=Severity.CRITICAL,
            description="Empty except block",
            file_path=Path("test.py"),
            line=10,
            code_snippet="except Exception: pass",
            suggested_fix="Replace pass with raise",
            confidence=0.95,
        ))
        report.slop_score = 75.0

        md = report.to_markdown()
        assert "# Unslop Report" in md
        assert "75/100" in md
        assert "AI-looking" in md
        assert "🔴 critical" in md
        assert "empty_error_handling" in md
        assert "line 10" in md
        assert "except Exception: pass" in md

    def test_to_markdown_file_vs_codebase(self) -> None:
        """Markdown shows file path for file-level, repository for codebase."""
        # File-level
        report = UnslopReport(file_path=Path("test.py"))
        md = report.to_markdown()
        assert "**File:**" in md

        # Codebase-level
        report = UnslopReport()
        md = report.to_markdown()
        assert "**Repository:**" in md

    def test_to_json_empty(self) -> None:
        """JSON of empty report has correct structure."""
        report = UnslopReport()
        data = report.to_json()
        assert data["version"] == "1.0"
        assert data["slop_score"] == 0.0
        assert data["issues"] == []
        assert data["by_tell"] == {}

    def test_to_json_with_issues(self) -> None:
        """JSON with issues has correct structure."""
        report = UnslopReport(file_path=Path("test.py"))
        report.add_issue(UnslopIssue(
            tell=TellCategory.EMPTY_ERROR_HANDLING,
            severity=Severity.CRITICAL,
            description="Empty except block",
            file_path=Path("test.py"),
            line=10,
            code_snippet="except Exception: pass",
            suggested_fix="Replace pass with raise",
            confidence=0.95,
            research_source="McKelvey",
        ))
        report.slop_score = 75.0

        data = report.to_json()
        assert data["file_path"] == "test.py"
        assert data["slop_score"] == 75.0
        assert len(data["issues"]) == 1
        assert data["issues"][0]["tell"] == "empty_error_handling"
        assert data["issues"][0]["severity"] == "critical"
        assert data["issues"][0]["line"] == 10
        assert data["issues"][0]["confidence"] == 0.95
        assert "by_tell" in data
        assert "empty_error_handling" in data["by_tell"]

    def test_severity_label(self) -> None:
        """Slop score labels are correct."""
        # Clean
        report = UnslopReport(slop_score=15.0)
        md = report.to_markdown()
        assert "Clean" in md

        # Mostly clean
        report = UnslopReport(slop_score=35.0)
        md = report.to_markdown()
        assert "Mostly clean" in md

        # Mixed
        report = UnslopReport(slop_score=50.0)
        md = report.to_markdown()
        assert "Mixed" in md

        # AI-looking
        report = UnslopReport(slop_score=70.0)
        md = report.to_markdown()
        assert "AI-looking" in md

        # Slop
        report = UnslopReport(slop_score=90.0)
        md = report.to_markdown()
        assert "Slop" in md
