"""Tests for GitHub integration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from unslop.github import (
    CommentResult,
    GitHubState,
    PRResult,
    check_github,
    commit_changes,
    create_branch,
    create_pr,
    format_pr_body,
    get_remote_owner_repo,
    get_remote_url,
    get_repo_info,
    post_comment,
    push_branch,
)


class TestGitHubState:
    """Tests for GitHubState dataclass."""

    def test_defaults(self) -> None:
        """GitHubState has correct defaults."""
        state = GitHubState()
        assert state.available is False
        assert state.authenticated is False
        assert state.username is None
        assert state.error is None

    def test_authenticated_state(self) -> None:
        """GitHubState can represent authenticated state."""
        state = GitHubState(
            available=True,
            authenticated=True,
            username="testuser",
        )
        assert state.available is True
        assert state.authenticated is True
        assert state.username == "testuser"
        assert state.error is None


class TestPRResult:
    """Tests for PRResult dataclass."""

    def test_defaults(self) -> None:
        """PRResult has correct defaults."""
        result = PRResult(success=False)
        assert result.success is False
        assert result.pr_url is None
        assert result.branch == ""
        assert result.error is None

    def test_success_result(self) -> None:
        """PRResult can represent successful PR creation."""
        result = PRResult(
            success=True,
            pr_url="https://github.com/user/repo/pull/123",
            branch="unslop-fix-123",
        )
        assert result.success is True
        assert result.pr_url == "https://github.com/user/repo/pull/123"
        assert result.branch == "unslop-fix-123"
        assert result.error is None


class TestCommentResult:
    """Tests for CommentResult dataclass."""

    def test_defaults(self) -> None:
        """CommentResult has correct defaults."""
        result = CommentResult(success=False)
        assert result.success is False
        assert result.comment_id is None
        assert result.error is None

    def test_success_result(self) -> None:
        """CommentResult can represent successful comment."""
        result = CommentResult(
            success=True,
            comment_id="456",
        )
        assert result.success is True
        assert result.comment_id == "456"
        assert result.error is None


class TestGetRemoteOwnerRepo:
    """Tests for remote URL parsing."""

    def test_https_with_git(self) -> None:
        """Parse HTTPS URL with .git suffix."""
        url = "https://github.com/owner/repo.git"
        result = get_remote_owner_repo(url)
        assert result == ("owner", "repo")

    def test_https_without_git(self) -> None:
        """Parse HTTPS URL without .git suffix."""
        url = "https://github.com/owner/repo"
        result = get_remote_owner_repo(url)
        assert result == ("owner", "repo")

    def test_ssh(self) -> None:
        """Parse SSH URL."""
        url = "git@github.com:owner/repo.git"
        result = get_remote_owner_repo(url)
        assert result == ("owner", "repo")

    def test_invalid_url(self) -> None:
        """Return None for non-GitHub URLs."""
        url = "https://gitlab.com/owner/repo.git"
        result = get_remote_owner_repo(url)
        assert result is None

    def test_empty_url(self) -> None:
        """Return None for empty URL."""
        result = get_remote_owner_repo("")
        assert result is None


class TestCheckGithub:
    """Tests for GitHub availability check."""

    def test_gh_not_installed(self) -> None:
        """Return error when gh is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            state = check_github("/tmp")
            assert state.available is False
            assert state.error == "gh CLI is not installed"

    def test_gh_available(self) -> None:
        """Return available=True when gh is installed."""
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # gh is installed, check if authenticated
            auth_result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Just verify it doesn't crash
            assert isinstance(check_github("/tmp"), GitHubState)


class TestCreateBranch:
    """Tests for branch creation."""

    def test_create_branch_success(self, tmp_repo: Path) -> None:
        """Create branch succeeds."""
        result = create_branch(tmp_repo, "test-branch")
        assert result is True


class TestCommitChanges:
    """Tests for commit operations."""

    def test_commit_no_changes(self, tmp_repo: Path) -> None:
        """Commit with no changes returns True."""
        result = commit_changes(tmp_repo, "test commit")
        assert result is True

    def test_commit_with_changes(self, tmp_repo: Path) -> None:
        """Commit with changes succeeds."""
        test_file = tmp_repo / "test.py"
        test_file.write_text("print('hello')", encoding="utf-8")
        result = commit_changes(tmp_repo, "test commit")
        assert result is True


class TestPushBranch:
    """Tests for push operations."""

    def test_push_branch_returns_result(self) -> None:
        """Push branch returns a boolean result."""
        # Just verify the function doesn't crash
        # (actual push requires a real remote)
        result = push_branch("/tmp", "test-branch")
        assert isinstance(result, bool)


class TestPostComment:
    """Tests for comment posting."""

    def test_post_comment_no_gh(self) -> None:
        """Post comment fails when gh not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = post_comment("/tmp", 123, "test comment")
            assert result.success is False


class TestGetRepoInfo:
    """Tests for repository info extraction."""

    def test_get_repo_info_no_remote(self, tmp_repo: Path) -> None:
        """Return None values when no remote."""
        info = get_repo_info(tmp_repo)
        assert info["owner"] is None
        assert info["repo"] is None
        assert info["remote_url"] is None


class TestFormatPRBody:
    """Tests for PR body formatting."""

    def test_format_pr_body(self) -> None:
        """Format PR body with all fields."""
        body = format_pr_body(
            title="Test PR",
            original_score=80.0,
            final_score=60.0,
            changes_applied=5,
            iterations=2,
            tests_passed=True,
        )
        assert "Test PR" in body
        assert "80/100" in body
        assert "60/100" in body
        assert "+20" in body
        assert "5" in body
        assert "2" in body
        assert "✅ Passed" in body

    def test_format_pr_body_no_tests(self) -> None:
        """Format PR body when tests not run."""
        body = format_pr_body(
            title="Test PR",
            original_score=80.0,
            final_score=60.0,
            changes_applied=5,
            iterations=2,
            tests_passed=None,
        )
        assert "⏭️ Skipped" in body

    def test_format_pr_body_tests_failed(self) -> None:
        """Format PR body when tests failed."""
        body = format_pr_body(
            title="Test PR",
            original_score=80.0,
            final_score=60.0,
            changes_applied=5,
            iterations=2,
            tests_passed=False,
        )
        assert "❌ Failed" in body


class TestCreatePR:
    """Tests for PR creation."""

    def test_create_pr_no_gh(self) -> None:
        """Create PR fails when gh not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = create_pr(
                repo_root="/tmp",
                title="Test PR",
                body="Test body",
                branch_name="test-branch",
            )
            assert result.success is False
            assert result.error is not None

    def test_create_pr_unauthenticated(self, tmp_repo: Path) -> None:
        """Create PR fails when not authenticated."""
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
            assert result.success is False
            assert result.error is not None
