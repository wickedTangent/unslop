"""GitHub integration for unslop.

Uses the `gh` CLI for all GitHub operations:
- Authentication via `gh auth status`
- Branch/commit management
- PR creation and commenting

Design principles:
- Never store tokens (use `gh auth` or `GITHUB_TOKEN` env var)
- All operations are reversible (git branch/commit can be deleted)
- Fail gracefully if `gh` is not available or not authenticated
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class GitHubState:
    """Result of checking GitHub availability."""
    available: bool = False
    authenticated: bool = False
    username: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PRResult:
    """Result of creating a PR."""
    success: bool
    pr_url: Optional[str] = None
    branch: str = ""
    error: Optional[str] = None


@dataclass
class CommentResult:
    """Result of posting a comment."""
    success: bool
    comment_id: Optional[str] = None
    error: Optional[str] = None


def check_github(repo_root: str | Path) -> GitHubState:
    """Check if `gh` CLI is available and authenticated.

    Args:
        repo_root: Path to repository root.

    Returns:
        GitHubState with availability and auth status.
    """
    repo_root = Path(repo_root).resolve()

    # Check if gh is installed
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return GitHubState(
                available=False,
                error="gh CLI is not installed",
            )
    except FileNotFoundError:
        return GitHubState(
            available=False,
            error="gh CLI is not installed",
        )
    except subprocess.TimeoutExpired:
        return GitHubState(
            available=False,
            error="gh CLI timed out",
        )

    # Check authentication
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return GitHubState(
                available=True,
                authenticated=False,
                error="Not authenticated with GitHub",
            )

        # Extract username from auth status output
        username = None
        for line in result.stdout.splitlines():
            match = re.search(r"account\s+(\S+)", line)
            if match:
                username = match.group(1)
                break

        return GitHubState(
            available=True,
            authenticated=True,
            username=username,
        )
    except subprocess.TimeoutExpired:
        return GitHubState(
            available=True,
            authenticated=False,
            error="gh auth status timed out",
        )


def get_remote_url(repo_root: str | Path) -> Optional[str]:
    """Get the GitHub remote URL for the repository.

    Args:
        repo_root: Path to repository root.

    Returns:
        Remote URL (e.g., https://github.com/user/repo.git) or None.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_remote_owner_repo(remote_url: str) -> Optional[tuple[str, str]]:
    """Extract owner and repo from a GitHub remote URL.

    Handles:
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git
    - https://github.com/owner/repo (without .git)

    Args:
        remote_url: The remote URL.

    Returns:
        Tuple of (owner, repo) or None.
    """
    # HTTPS: https://github.com/owner/repo.git
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/\s.]+)(?:\.git)?$",
        remote_url,
    )
    if match:
        return match.group(1), match.group(2)

    # SSH: git@github.com:owner/repo.git
    match = re.match(
        r"git@github\.com:([^/]+)/([^/\s.]+)(?:\.git)?$",
        remote_url,
    )
    if match:
        return match.group(1), match.group(2)

    return None


def create_branch(repo_root: str | Path, branch_name: str) -> bool:
    """Create a new git branch and switch to it.

    Args:
        repo_root: Path to repository root.
        branch_name: Name of the branch to create.

    Returns:
        True if branch was created successfully.
    """
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def commit_changes(
    repo_root: str | Path,
    message: str,
    author_name: Optional[str] = None,
    author_email: Optional[str] = None,
) -> bool:
    """Stage and commit all changes.

    Args:
        repo_root: Path to repository root.
        message: Commit message.
        author_name: Author name (uses git config if None).
        author_email: Author email (uses git config if None).

    Returns:
        True if commit was created successfully.
    """
    try:
        subprocess.run(
            ["git", "add", "."],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
        )

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_root),
        )
        if not result.stdout.strip():
            return True  # Nothing to commit

        # Commit
        cmd = ["git", "commit", "-m", message]
        if author_name and author_email:
            cmd = [
                "git", "commit", "-m", message,
                "--author", f"{author_name} <{author_email}>",
            ]
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def push_branch(
    repo_root: str | Path,
    branch_name: str,
    set_upstream: bool = True,
) -> bool:
    """Push a branch to the remote.

    Args:
        repo_root: Path to repository root.
        branch_name: Name of the branch to push.
        set_upstream: Whether to set the upstream tracking branch.

    Returns:
        True if push was successful.
    """
    try:
        cmd = ["git", "push"]
        if set_upstream:
            cmd.extend(["-u", "origin", branch_name])
        else:
            cmd.extend(["origin", branch_name])
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(repo_root),
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def create_pr(
    repo_root: str | Path,
    title: str,
    body: str,
    branch_name: str,
    base_branch: str = "main",
) -> PRResult:
    """Create a GitHub Pull Request using `gh pr create`.

    Args:
        repo_root: Path to repository root.
        title: PR title.
        body: PR body (Markdown).
        branch_name: Source branch.
        base_branch: Target branch (default: main).

    Returns:
        PRResult with success status and PR URL.
    """
    state = check_github(repo_root)
    if not state.available:
        return PRResult(
            success=False,
            error=state.error or "gh CLI not available",
        )

    if not state.authenticated:
        return PRResult(
            success=False,
            error=state.error or "Not authenticated with GitHub",
        )

    try:
        # Use gh pr create with --head, --base, and body from stdin
        proc = subprocess.run(
            ["gh", "pr", "create", "--head", branch_name,
             "--base", base_branch, "--title", title, "--body", "-"],
            input=body,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(repo_root),
        )
        if proc.returncode != 0:
            error_msg = proc.stderr.strip()
            # Extract PR URL if gh printed one despite non-zero exit
            pr_match = re.search(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+",
                                  proc.stderr)
            if pr_match:
                return PRResult(
                    success=True,
                    pr_url=pr_match.group(0),
                    branch=branch_name,
                )
            return PRResult(
                success=False,
                error=error_msg,
                branch=branch_name,
            )

        # Extract PR URL from output
        pr_url = None
        for line in proc.stdout.splitlines():
            if "https://github.com" in line and "/pull/" in line:
                pr_url = line.strip()
                break

        return PRResult(
            success=True,
            pr_url=pr_url,
            branch=branch_name,
        )
    except subprocess.TimeoutExpired:
        return PRResult(
            success=False,
            error="gh pr create timed out",
            branch=branch_name,
        )
    except FileNotFoundError:
        return PRResult(
            success=False,
            error="gh CLI not found",
            branch=branch_name,
        )


def post_comment(
    repo_root: str | Path,
    pr_number: int,
    body: str,
) -> CommentResult:
    """Post a comment on a GitHub PR.

    Args:
        repo_root: Path to repository root.
        pr_number: PR number.
        body: Comment body (Markdown).

    Returns:
        CommentResult with success status.
    """
    state = check_github(repo_root)
    if not state.available or not state.authenticated:
        return CommentResult(
            success=False,
            error="gh CLI not available or not authenticated",
        )

    try:
        result = subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--body", "-"],
            input=body,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repo_root),
        )
        if result.returncode != 0:
            return CommentResult(
                success=False,
                error=result.stderr.strip(),
            )

        # Extract comment ID from output
        comment_id = None
        for line in result.stdout.splitlines():
            match = re.search(r"#(\d+)", line)
            if match:
                comment_id = match.group(1)
                break

        return CommentResult(
            success=True,
            comment_id=comment_id,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return CommentResult(
            success=False,
            error="gh pr comment failed",
        )


def get_repo_info(repo_root: str | Path) -> dict:
    """Get repository info (owner, repo, remote URL).

    Args:
        repo_root: Path to repository root.

    Returns:
        Dictionary with owner, repo, remote_url keys.
    """
    remote_url = get_remote_url(repo_root)
    if not remote_url:
        return {"owner": None, "repo": None, "remote_url": None}

    owner_repo = get_remote_owner_repo(remote_url)
    if not owner_repo:
        return {"owner": None, "repo": None, "remote_url": remote_url}

    return {
        "owner": owner_repo[0],
        "repo": owner_repo[1],
        "remote_url": remote_url,
    }


def format_pr_body(
    title: str,
    original_score: float,
    final_score: float,
    changes_applied: int,
    iterations: int,
    tests_passed: Optional[bool],
) -> str:
    """Format a PR body from fix pipeline results.

    Args:
        title: PR title.
        original_score: Original slop score.
        final_score: Final slop score after fixes.
        changes_applied: Number of changes applied.
        iterations: Number of fix iterations.
        tests_passed: Whether tests passed.

    Returns:
        Formatted Markdown PR body.
    """
    delta = original_score - final_score
    lines = [
        f"# Unslop Fix — {title}",
        "",
        "## Summary",
        "",
        f"- **Original score:** {original_score:.0f}/100",
        f"- **Final score:** {final_score:.0f}/100",
        f"- **Improvement:** {delta:+.0f} points",
        f"- **Changes applied:** {changes_applied}",
        f"- **Iterations:** {iterations}",
        f"- **Tests:** {'✅ Passed' if tests_passed else ('❌ Failed' if tests_passed is False else '⏭️ Skipped')}",
        "",
        "## What Changed",
        "",
        f"This PR was generated by `unslop fix` to remove AI-generated code patterns.",
        "",
        "### Auto-fixed tells",
        "",
        "The following AI tells were automatically fixed:",
        "",
        "| Tell | Severity | Action |",
        "|------|----------|--------|",
        "| Empty error handling | High | Replaced `pass` with `raise` |",
        "| Dead code | Medium | Removed unused imports |",
        "| Dependency bloat | Medium | Removed unused imports |",
        "| Verbose comments | Low | Removed observable restatements |",
        "| TODO artifacts | Low | Removed TODO/FIXME/HACK comments |",
        "| Debug artifacts | Low | Removed console.log/print/debugger |",
        "",
        "## Next Steps",
        "",
        "1. Review the changes in this PR",
        "2. Run tests locally to verify",
        "3. Merge when satisfied",
        "",
        f"*Generated by [unslop](https://github.com/FUTR-Network/unslop) — polish AI-generated code to human quality*",
    ]
    return "\n".join(lines)
