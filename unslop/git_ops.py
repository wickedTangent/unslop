"""Git operations for unslop fix pipeline.

Provides clean-tree verification, diff capture, and revert functionality.
All operations are safe — they never force-destroy changes without user consent.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GitState:
    """Snapshot of git state for diff capture and revert."""
    has_repo: bool
    is_dirty: bool
    diff_before: str = ""


def check_clean_tree(repo_root: Path) -> GitState:
    """Check if the git working tree is clean.

    Only checks for modified/staged files — untracked files are ignored
    (they won't be lost on revert).

    Args:
        repo_root: Path to repository root.

    Returns:
        GitState with clean/dirty status.
    """
    try:
        # --porcelain shows all changes, but we only care about modified/staged
        # Untracked files (??) are harmless — won't be lost on revert
        result = subprocess.run(
            ["git", "status", "--porcelain", "-u", "no"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        is_dirty = bool(result.stdout.strip())
        has_repo = result.returncode == 0
        return GitState(has_repo=has_repo, is_dirty=is_dirty)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return GitState(has_repo=False, is_dirty=False)


def capture_diff(repo_root: Path) -> GitState:
    """Capture the current git diff and state.

    This is called BEFORE applying fixes, so it captures the "clean" state.

    Args:
        repo_root: Path to repository root.

    Returns:
        GitState with diff captured.
    """
    state = check_clean_tree(repo_root)
    if not state.has_repo:
        return state

    try:
        result = subprocess.run(
            ["git", "diff"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        state.diff_before = result.stdout
        return state
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return state


def revert_changes(repo_root: Path) -> bool:
    """Revert all changes to HEAD.

    This is called when tests fail — restores the repo to its pre-fix state.

    Args:
        repo_root: Path to repository root.

    Returns:
        True if revert succeeded, False otherwise.
    """
    try:
        # First, discard any unstaged changes
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Then hard reset to HEAD
        result = subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_branch_name(repo_root: Path) -> Optional[str]:
    """Get the current branch name.

    Args:
        repo_root: Path to repository root.

    Returns:
        Branch name string, or None if not in a repo / no branch.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_current_commit(repo_root: Path) -> Optional[str]:
    """Get the current commit hash.

    Args:
        repo_root: Path to repository root.

    Returns:
        Commit hash string (short form), or None if not in a repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
