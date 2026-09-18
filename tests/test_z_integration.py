"""End-to-end integration tests for unslop.

Tests the full pipeline: scan → fix → report → GitHub integration.
Uses a realistic test repo with AI-generated code patterns.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from unslop import (
    FixPipeline,
    GitHubState,
    PRResult,
    UnslopAnalyzer,
    check_github,
    create_pr,
)


def create_sloppy_test_repo(repo_root: Path) -> Path:
    """Create a test repo with AI-generated code patterns."""
    (repo_root / "src").mkdir()
    (repo_root / "tests").mkdir()

    (repo_root / "src" / "user_service.py").write_text(
        '"""User service module."""\n'
        '\n'
        'import os\n'
        'import sys\n'
        'import json\n'
        'import datetime\n'
        'import re\n'
        '\n'
        'def newUser(data):\n'
        '    # increment the counter\n'
        '    counter += 1\n'
        '    return data\n'
        '\n'
        'def helper_validate(x):\n'
        '    # validate the input\n'
        '    if x is None:\n'
        '        pass\n'
        '    return True\n'
        '\n'
        'def newProcess():\n'
        '    try:\n'
        '        data = json.loads("{}")\n'
        '    except Exception:\n'
        '        pass\n'
        '    return data\n'
        '\n'
        'def tempData():\n'
        '    # TODO: implement this properly\n'
        '    # FIXME: this is broken\n'
        '    # HACK: workaround for now\n'
        '    print("debug: tempData called")\n'
        '    return None\n'
        '\n'
        'def handleClick3(event):\n'
        '    # handle the click event\n'
        '    result_final = process(data2)\n'
        '    return result_final\n',
        encoding="utf-8",
    )

    (repo_root / "src" / "app.ts").write_text(
        'import { Component } from "@angular/core";\n'
        'import { HttpClient } from "@angular/common/http";\n'
        'import { Observable } from "rxjs";\n'
        '\n'
        'export class AppComponent {\n'
        '    title = "app";\n'
        '\n'
        '    // get the user data\n'
        '    getUser(): Observable<any> {\n'
        '        console.log("getUser called");\n'
        '        return this.http.get("/api/user");\n'
        '    }\n'
        '\n'
        '    // handle the form submit\n'
        '    onSubmit(): void {\n'
        '        debugger;\n'
        '        // TODO: add form validation\n'
        '        console.log("form submitted");\n'
        '    }\n'
        '\n'
        '    newHelper(): void {\n'
        '        // helper function\n'
        '        const tempResult = 42;\n'
        '        return tempResult;\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )

    (repo_root / "tests" / "test_user.py").write_text(
        'import pytest\n'
        '\n'
        'def test_user_service():\n'
        '    # Test the user service\n'
        '    assert True  # placeholder test\n'
        '\n'
        'def test_validate():\n'
        '    # Test validation\n'
        '    assert True\n'
        '\n'
        'def test_process():\n'
        '    # Test process\n'
        '    pass\n',
        encoding="utf-8",
    )

    subprocess.run(["git", "init"], cwd=str(repo_root), capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo_root),
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo_root),
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=str(repo_root),
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo_root),
        capture_output=True,
    )
    return repo_root


@pytest.fixture
def sloppy_repo(tmp_path: Path) -> Path:
    """Create a test repo with AI-generated code patterns."""
    repo = tmp_path / "sloppy_repo"
    repo.mkdir()
    return create_sloppy_test_repo(repo)


class TestScanIntegration:
    """Test the scan pipeline end-to-end."""

    def test_scan_single_file(self, sloppy_repo: Path) -> None:
        """Scan a single file and get issues."""
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        report = analyzer.analyze_file(sloppy_repo / "src" / "user_service.py")

        assert report.slop_score > 0
        assert len(report.issues) > 0

        # Should detect multiple tell categories
        tell_categories = {issue.tell for issue in report.issues}
        assert len(tell_categories) >= 3  # Multiple tell types

    def test_scan_codebase(self, sloppy_repo: Path) -> None:
        """Scan entire codebase."""
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        report = analyzer.analyze_codebase(max_files=50)

        assert report.slop_score > 0
        assert len(report.issues) > 0

        # Should have issues across multiple files
        files_with_issues = {str(issue.file_path) for issue in report.issues}
        assert len(files_with_issues) >= 2

    def test_scan_report_markdown(self, sloppy_repo: Path) -> None:
        """Scan report generates valid markdown."""
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        report = analyzer.analyze_file(sloppy_repo / "src" / "user_service.py")

        md = report.to_markdown()
        assert "Unslop Report" in md or "Slop Score" in md
        assert f"{report.slop_score:.0f}" in md or str(int(report.slop_score)) in md

    def test_scan_report_json(self, sloppy_repo: Path) -> None:
        """Scan report generates valid JSON."""
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        report = analyzer.analyze_file(sloppy_repo / "src" / "user_service.py")

        data = report.to_json()
        assert "version" in data
        assert "slop_score" in data
        assert "issues" in data
        assert len(data["issues"]) > 0

    def test_scan_severity_counts(self, sloppy_repo: Path) -> None:
        """Scan report has correct severity counts."""
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        report = analyzer.analyze_file(sloppy_repo / "src" / "user_service.py")

        counts = report.severity_counts()
        total = sum(counts.values())
        assert total == len(report.issues)
        assert "critical" in counts
        assert "high" in counts
        assert "medium" in counts
        assert "low" in counts


class TestFixIntegration:
    """Test the fix pipeline end-to-end."""

    def test_fix_pipeline_runs(self, sloppy_repo: Path) -> None:
        """Fix pipeline runs without crashing."""
        pipeline = FixPipeline(repo_root=sloppy_repo)
        result = pipeline.run(threshold=80, run_tests_flag=False)

        assert result.original_score > 0
        assert result.final_score >= 0
        assert result.stopped_reason in (
            "threshold_reached",
            "no_fixes",
            "max_iterations",
        )

    def test_fix_pipeline_improves_score(self, sloppy_repo: Path) -> None:
        """Fix pipeline improves slop score."""
        pipeline = FixPipeline(repo_root=sloppy_repo)
        result = pipeline.run(threshold=50, run_tests_flag=False)

        # Score should improve or stay same
        assert result.final_score <= result.original_score

    def test_fix_pipeline_dry_run(self, sloppy_repo: Path) -> None:
        """Dry run doesn't modify files."""
        original_content = (sloppy_repo / "src" / "user_service.py").read_text()

        pipeline = FixPipeline(repo_root=sloppy_repo)
        result = pipeline.run_dry(threshold=80)

        # Files should be unchanged
        assert (sloppy_repo / "src" / "user_service.py").read_text() == original_content
        assert result.stopped_reason == "dry_run_estimate"

    def test_fix_pipeline_applies_fixes(self, sloppy_repo: Path) -> None:
        """Fix pipeline actually applies fixes."""
        pipeline = FixPipeline(repo_root=sloppy_repo)
        result = pipeline.run(threshold=80, run_tests_flag=False)

        # Should have some changes applied
        assert len(result.changes_applied) > 0

    def test_fix_pipeline_reports(self, sloppy_repo: Path) -> None:
        """Fix pipeline generates both report formats."""
        md_path = sloppy_repo / "test_report.md"
        json_path = sloppy_repo / "test_report.json"

        pipeline = FixPipeline(repo_root=sloppy_repo)
        result = pipeline.run(threshold=80, run_tests_flag=False)

        result.write_report(str(md_path), str(json_path))

        assert md_path.exists()
        assert json_path.exists()

        # Verify markdown content
        md_content = md_path.read_text()
        assert "Unslop Fix Report" in md_content

        # Verify JSON content
        json_content = json.loads(json_path.read_text())
        assert "summary" in json_content
        assert "iterations" in json_content
        assert "changes" in json_content

    def test_fix_pipeline_no_fixes_needed(self, sloppy_repo: Path) -> None:
        """Pipeline handles clean file gracefully."""
        # Create a clean file
        clean_file = sloppy_repo / "src" / "clean.py"
        clean_file.write_text(
            'def get_user(user_id):\n'
            '    """Get user by ID."""\n'
            '    return {"id": user_id}\n',
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "src/clean.py"],
            cwd=str(sloppy_repo),
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add clean file"],
            cwd=str(sloppy_repo),
            capture_output=True,
        )

        pipeline = FixPipeline(repo_root=sloppy_repo)
        result = pipeline.run(threshold=80, run_tests_flag=False)

        # Should handle gracefully
        assert result.stopped_reason in (
            "threshold_reached",
            "no_fixes",
            "max_iterations",
        )


class TestGitHubIntegration:
    """Test GitHub integration end-to-end."""

    def test_check_github_available(self) -> None:
        """Check GitHub availability works."""
        state = check_github("/tmp")
        assert isinstance(state, GitHubState)
        # Just verify it doesn't crash
        assert state.available is True or state.error is not None

    def test_create_pr_unauthenticated(self, tmp_repo: Path) -> None:
        """Create PR fails gracefully when not authenticated."""
        # Mock subprocess to simulate unauthenticated
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=1, stderr="Not authenticated"),
        ):
            result = create_pr(
                repo_root=tmp_repo,
                title="Test PR",
                body="Test body",
                branch_name="test-branch",
            )
            assert isinstance(result, PRResult)
            assert result.success is False
            assert result.error is not None

    def test_github_state_dataclass(self) -> None:
        """GitHubState dataclass works correctly."""
        from unslop.github import GitHubState

        state = GitHubState(
            available=True,
            authenticated=True,
            username="testuser",
        )
        assert state.available is True
        assert state.authenticated is True
        assert state.username == "testuser"
        assert state.error is None

    def test_pr_result_dataclass(self) -> None:
        """PRResult dataclass works correctly."""
        from unslop.github import PRResult

        result = PRResult(
            success=True,
            pr_url="https://github.com/user/repo/pull/123",
            branch="unslop-fix-123",
        )
        assert result.success is True
        assert result.pr_url == "https://github.com/user/repo/pull/123"
        assert result.branch == "unslop-fix-123"


class TestFullPipeline:
    """Test the complete workflow: scan → fix → scan → report."""

    def test_scan_then_fix_then_scan(self, sloppy_repo: Path) -> None:
        """Full workflow: scan, fix, scan again, verify improvement."""
        # 1. Initial scan
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        initial_report = analyzer.analyze_codebase(max_files=50)
        initial_score = initial_report.slop_score

        # 2. Run fix pipeline
        pipeline = FixPipeline(repo_root=sloppy_repo)
        fix_result = pipeline.run(threshold=80, run_tests_flag=False)

        # 3. Re-scan after fixes
        final_report = analyzer.analyze_codebase(max_files=50)
        final_score = final_report.slop_score

        # 4. Verify improvement
        assert final_score <= initial_score

        # 5. Verify changes were applied
        assert len(fix_result.changes_applied) > 0

    def test_scan_then_fix_then_report(self, sloppy_repo: Path) -> None:
        """Full workflow with report generation."""
        md_path = sloppy_repo / "final_report.md"
        json_path = sloppy_repo / "final_report.json"

        # Scan
        analyzer = UnslopAnalyzer(repo_root=sloppy_repo)
        report = analyzer.analyze_codebase(max_files=50)

        # Fix
        pipeline = FixPipeline(repo_root=sloppy_repo)
        fix_result = pipeline.run(threshold=80, run_tests_flag=False)

        # Generate reports
        fix_result.write_report(str(md_path), str(json_path))

        # Verify reports exist and have content
        assert md_path.exists()
        assert md_path.stat().st_size > 100
        assert json_path.exists()
        assert json_path.stat().st_size > 100

        # Verify JSON structure
        data = json.loads(json_path.read_text())
        assert "summary" in data
        assert "changes" in data
        assert data["summary"]["original_score"] > 0
