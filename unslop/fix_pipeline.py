"""Fix pipeline — iterative scan → fix → test → re-scan loop.

Orchestrates the unslop fix workflow:
1. Scan the codebase for AI tells
2. Apply safe fixes (Tier 1 and Tier 2)
3. Run tests to verify changes
4. Re-scan to measure improvement
5. Repeat until target score reached or tests fail

Safety tiers:
- Tier 1 (no test gate): verbose_comments, todo_artifacts, debug_artifacts
- Tier 2 (test-gated): empty_error_handling, dead_code
- Tier 3 (never auto): naming, pattern, dependency_bloat, security, test_quality, volume, cross_file

Design principles:
- Never leave artifacts behind (no .unslopped files)
- Always reversible (git diff captured, revert on test failure)
- Confidence-scored (low-confidence fixes skipped)
- Agent-readable (structured JSON report)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .analyzer import UnslopAnalyzer
from .git_ops import (
    check_clean_tree,
    capture_diff,
    get_branch_name,
    get_current_commit,
    revert_changes,
)
from .report import Severity, TellCategory, UnslopReport
from .test_runner import TestResult, run_tests


# Safety tier classification
TIER_1_ALWAYS_SAFE = {
    TellCategory.VERBOSE_COMMENTS,
    TellCategory.TODO_ARTIFACTS,
    TellCategory.DEBUG_ARTIFACTS,
}

TIER_2_TEST_GATED = {
    TellCategory.EMPTY_ERROR_HANDLING,
    TellCategory.DEAD_CODE,
    TellCategory.DEPENDENCY_BLOAT,
}

# Tier 3 tells are never auto-applied (not listed here — excluded by default)


@dataclass
class FixIteration:
    """Record of a single iteration in the fix loop."""
    iteration: int
    start_score: float
    end_score: float
    fixes_applied: int
    tests_passed: Optional[bool] = None
    test_result: Optional[TestResult] = None


@dataclass
class FixChange:
    """Record of a single fix change."""
    file_path: str
    line: Optional[int]
    tell: TellCategory
    severity: Severity
    confidence: float
    tier: int  # 1, 2, or 3
    action: str  # "removed", "changed", "suggested"
    original: Optional[str] = None
    reasoning: Optional[str] = None
    safe_to_revert: bool = True


@dataclass
class FixResult:
    """Complete result of a fix pipeline run."""
    original_score: float
    final_score: float
    iterations: list[FixIteration] = field(default_factory=list)
    changes_applied: list[FixChange] = field(default_factory=list)
    changes_not_applied: list[dict] = field(default_factory=list)
    files_modified: list[dict] = field(default_factory=list)
    tests_passed: Optional[bool] = None
    test_command: str = ""
    time_seconds: float = 0.0
    stopped_reason: str = ""  # "threshold_reached", "tests_failed", "max_iterations", "no_fixes"
    _repo_root: Optional[Path] = None  # Internal, for report generation

    def to_markdown(self) -> str:
        """Generate a human-readable Markdown fix report."""
        lines = []
        lines.append("# Unslop Fix Report\n")

        # Stop reason display
        reason_display = {
            "threshold_reached": "Target score reached",
            "tests_failed": "Tests failed — changes reverted",
            "max_iterations": "Maximum iterations reached",
            "no_fixes": "No applicable fixes found",
            "dirty_working_tree": "Working tree not clean — aborting",
            "not_a_git_repo": "Not a git repository",
        }

        # Summary
        lines.append(f"**Repository:** `{self._repo_root}`\n")
        lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
        lines.append(f"**Stops reason:** {reason_display.get(self.stopped_reason, self.stopped_reason)}\n")

        # Score summary
        delta = self.original_score - self.final_score
        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Original score | {self.original_score:.0f}/100 |")
        lines.append(f"| Final score | {self.final_score:.0f}/100 |")
        lines.append(f"| Score improvement | {delta:+.0f} |")
        lines.append(f"| Changes applied | {len(self.changes_applied)} |")
        lines.append(f"| Iterations | {len(self.iterations)} |")
        if self.tests_passed is not None:
            icon = "✅" if self.tests_passed else "❌"
            lines.append(f"| Tests passed | {icon} |")
        lines.append(f"| Time elapsed | {self.time_seconds:.1f}s |")
        lines.append("")

        # Iteration history
        if self.iterations:
            lines.append("## Iteration History\n")
            for it in self.iterations:
                lines.append(f"### Iteration {it.iteration}\n")
                lines.append(f"- **Start score:** {it.start_score:.0f}/100")
                lines.append(f"- **End score:** {it.end_score:.0f}/100")
                lines.append(f"- **Fixes applied:** {it.fixes_applied}")
                if it.tests_passed is not None:
                    icon = "✅" if it.tests_passed else "❌"
                    lines.append(f"- **Tests:** {icon}")
                lines.append("")

        # Changes applied
        if self.changes_applied:
            lines.append("## Changes Applied\n")
            for i, change in enumerate(self.changes_applied, 1):
                location = f"line {change.line}" if change.line else str(change.file_path)
                lines.append(f"### {i}. {change.tell.value} ({change.severity.value}) — `{change.file_path}:{location}`\n")
                lines.append(f"- **Action:** Removed issue")
                lines.append(f"- **Reasoning:** {change.reasoning or 'Common AI-generated code pattern.'}")
                lines.append(f"- **Confidence:** {change.confidence:.0%}")
                lines.append(f"- **Safe to revert:** {'Yes' if change.safe_to_revert else 'No'}")
                if change.original:
                    lang = "py" if change.file_path.endswith(".py") else "ts"
                    lines.append(f"- **Original:**")
                    lines.append(f"  ```{lang}")
                    lines.append(f"  {change.original[:100]}")
                    lines.append(f"  ```")
                lines.append("")

        # Changes not applied
        if self.changes_not_applied:
            lines.append("## Changes Not Applied\n")
            lines.append("| File | Line | Tell | Reason |")
            lines.append("|------|------|------|--------|")
            for item in self.changes_not_applied:
                location = f"line {item.get('line')}" if item.get('line') else str(item.get('file', '?'))
                lines.append(f"| `{item.get('file', '?')}` | {location} | {item.get('tell', '?')} | {item.get('reason', '?')} |")
            lines.append("")

        # Files modified
        if self.files_modified:
            lines.append("## Files Modified\n")
            lines.append("| File | Changes | Score impact |")
            lines.append("|------|---------|-------------|")
            for f in self.files_modified:
                lines.append(f"| `{f['file']}` | {f['changes']} | {f['score_impact']:+.0f} |")
            lines.append("")

        # Next steps
        lines.append("## Next Steps\n")
        lines.append("1. Review the changes above")
        if self.tests_passed:
            lines.append("2. Tests passed — changes are safe to keep")
            lines.append("3. Run `git diff` to see all changes")
            lines.append("4. If satisfied: commit and push")
            lines.append("5. If not: `git reset --hard` to revert")
        else:
            lines.append("2. ❌ Tests failed — all changes have been reverted")
            lines.append("3. Review the iteration history above to understand what was attempted")
            lines.append("4. `git status` to verify clean state")
        lines.append("")

        return "\n".join(lines)

    def to_json(self) -> dict:
        """Generate a structured JSON-serializable fix report."""
        return {
            "version": "1.0",
            "tool": "unslop",
            "command": "unslop fix",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repository": str(self._repo_root) if hasattr(self, "_repo_root") else None,
            "summary": {
                "original_score": round(self.original_score, 1),
                "final_score": round(self.final_score, 1),
                "score_delta": round(self.original_score - self.final_score, 1),
                "changes_applied": len(self.changes_applied),
                "iterations": len(self.iterations),
                "tests_passed": self.tests_passed,
                "test_command": self.test_command,
                "time_seconds": round(self.time_seconds, 1),
                "stopped_reason": self.stopped_reason,
            },
            "iterations": [
                {
                    "number": it.iteration,
                    "start_score": round(it.start_score, 1),
                    "end_score": round(it.end_score, 1),
                    "fixes_applied": it.fixes_applied,
                    "tests_passed": it.tests_passed,
                }
                for it in self.iterations
            ],
            "changes": [
                {
                    "file": change.file_path,
                    "line": change.line,
                    "tell": change.tell.value,
                    "severity": change.severity.value,
                    "confidence": round(change.confidence, 2),
                    "tier": change.tier,
                    "action": change.action,
                    "original": change.original,
                    "reasoning": change.reasoning,
                    "safe_to_revert": change.safe_to_revert,
                }
                for change in self.changes_applied
            ],
            "changes_not_applied": self.changes_not_applied,
            "files_modified": self.files_modified,
        }

    def write_report(self, md_path: str = "unslopped.md", json_path: Optional[str] = None) -> None:
        """Write reports to files.

        Args:
            md_path: Path for Markdown report.
            json_path: Path for JSON report. None to skip.
        """
        Path(md_path).write_text(self.to_markdown(), encoding="utf-8")
        if json_path:
            Path(json_path).write_text(
                json.dumps(self.to_json(), indent=2) + "\n",
                encoding="utf-8",
            )

    def __str__(self) -> str:
        """Human-readable summary for stdout."""
        delta = self.original_score - self.final_score
        status = "✅" if self.tests_passed else ("❌" if self.tests_passed is False else "?")
        lines = [
            f"Unslop Fix Result",
            f"Score: {self.original_score:.0f}/100 → {self.final_score:.0f}/100 ({delta:+.0f})",
            f"Changes: {len(self.changes_applied)} applied, {len(self.changes_not_applied)} skipped",
            f"Iterations: {len(self.iterations)}",
            f"Tests: {status}",
            f"Time: {self.time_seconds:.1f}s",
            f"Reason: {self.stopped_reason}",
        ]
        return "\n".join(lines)


class FixPipeline:
    """Iterative fix pipeline for unslop.

    Usage:
        pipeline = FixPipeline(repo_root="/path/to/repo")
        result = pipeline.run(threshold=40, run_tests=True)
        print(f"Score: {result.original_score} → {result.final_score}")
        result.to_markdown()  # Human-readable report
        result.to_json()      # Agent-readable report
    """

    def __init__(
        self,
        repo_root: str | Path,
        min_confidence: float = 0.80,
        max_iterations: int = 10,
        severity_filter: Optional[list[str]] = None,
    ) -> None:
        """Initialize the fix pipeline.

        Args:
            repo_root: Path to repository root.
            min_confidence: Minimum confidence (0-1) to apply a fix.
            max_iterations: Maximum scan→fix→test loop iterations.
            severity_filter: Severity levels to apply fixes for.
                None means all. Examples: ["critical", "high"], ["medium"].
        """
        self.repo_root = Path(repo_root).resolve()
        self.min_confidence = min_confidence
        self.max_iterations = max_iterations
        self.severity_filter = severity_filter or [s.value for s in Severity]
        self._analyzer = UnslopAnalyzer(repo_root=self.repo_root)

    def run(
        self,
        threshold: float = 40.0,
        run_tests_flag: bool = False,
        test_cmd: Optional[str] = None,
        test_timeout: int = 120,
    ) -> FixResult:
        """Run the full fix pipeline.

        Iterates: scan → apply safe fixes → run tests → re-scan
        until score < threshold, tests fail, or max iterations reached.

        Args:
            threshold: Target score (lower is better). Stop when score < threshold.
            run_tests_flag: Whether to run tests after each fix iteration.
            test_cmd: Override test command. Auto-detected if None.
            test_timeout: Maximum seconds for test execution.

        Returns:
            FixResult with full iteration history and change details.
        """
        start_time = time.time()
        result = FixResult(
            original_score=0.0,
            final_score=0.0,
            stopped_reason="",
            _repo_root=self.repo_root,
        )

        # 1. Verify clean working tree
        state = check_clean_tree(self.repo_root)
        if not state.has_repo:
            result.stopped_reason = "not_a_git_repo"
            result.time_seconds = time.time() - start_time
            return result

        if state.is_dirty:
            result.stopped_reason = "dirty_working_tree"
            result.time_seconds = time.time() - start_time
            return result

        # 2. Initial scan
        report = self._scan()
        result.original_score = report.slop_score
        result.final_score = report.slop_score

        # 3. Iteration loop
        prev_end_score = report.slop_score
        for iteration_num in range(1, self.max_iterations + 1):
            if report.slop_score < threshold:
                result.stopped_reason = "threshold_reached"
                result.final_score = report.slop_score
                break

            fixes_count, changes, files_info = self._apply_fixes(report)
            if fixes_count == 0:
                result.stopped_reason = "no_fixes"
                result.final_score = report.slop_score
                result.changes_applied = changes
                result.files_modified = files_info
                break

            # Re-scan after fixes
            report = self._scan()
            result.final_score = report.slop_score

            # Run tests if enabled
            test_result = None
            tests_passed = None
            if run_tests_flag:
                test_result = run_tests(
                    self.repo_root,
                    test_cmd=test_cmd,
                    timeout=test_timeout,
                )
                tests_passed = test_result.passed
                if test_result.command:
                    result.test_command = test_result.command

                if not tests_passed:
                    # Revert changes and stop
                    revert_changes(self.repo_root)
                    result.stopped_reason = "tests_failed"
                    result.tests_passed = False
                    result.changes_applied = changes
                    result.files_modified = files_info
                    result.time_seconds = time.time() - start_time
                    return result

            # Record iteration
            result.iterations.append(FixIteration(
                iteration=iteration_num,
                start_score=prev_end_score,
                end_score=report.slop_score,
                fixes_applied=fixes_count,
                tests_passed=tests_passed,
                test_result=test_result,
            ))

            # Update previous end score for next iteration
            prev_end_score = report.slop_score

            # Record changes and files
            result.changes_applied.extend(changes)
            result.files_modified.extend(files_info)

            # Rebuild report for next iteration
            report = self._scan()

        # If we exit the loop without breaking, set reason
        if not result.stopped_reason:
            if report.slop_score < threshold:
                result.stopped_reason = "threshold_reached"
            else:
                result.stopped_reason = "max_iterations"

        result.time_seconds = time.time() - start_time
        return result

    def run_dry(
        self,
        threshold: float = 40.0,
    ) -> FixResult:
        """Run a dry run — show what would change without applying anything.

        Args:
            threshold: Target score for display purposes.

        Returns:
            FixResult with predicted changes (no files modified).
        """
        start_time = time.time()
        result = FixResult(original_score=0.0, final_score=0.0, stopped_reason="")

        state = check_clean_tree(self.repo_root)
        if not state.has_repo:
            result.stopped_reason = "not_a_git_repo"
            result.time_seconds = time.time() - start_time
            return result

        if state.is_dirty:
            result.stopped_reason = "dirty_working_tree"
            result.time_seconds = time.time() - start_time
            return result

        # Initial scan
        report = self._scan()
        result.original_score = report.slop_score
        result.final_score = report.slop_score

        # Simulate iterations
        for iteration_num in range(1, self.max_iterations + 1):
            if report.slop_score < threshold:
                result.stopped_reason = "threshold_reached"
                result.final_score = report.slop_score
                break

            fixes_count = self._count_applicable_fixes(report)
            if fixes_count == 0:
                result.stopped_reason = "no_fixes"
                result.final_score = report.slop_score
                break

            # Estimate score improvement (rough heuristic)
            # Each Tier 1 fix removes ~2-3 points, Tier 2 removes ~5-8 points
            estimated_reduction = min(fixes_count * 2.0, 30.0)
            result.final_score = max(0.0, report.slop_score - estimated_reduction)

            result.iterations.append(FixIteration(
                iteration=iteration_num,
                start_score=report.slop_score,
                end_score=result.final_score,
                fixes_applied=fixes_count,
            ))

            result.stopped_reason = "dry_run_estimate"  # Dry run shows first iteration
            break  # Dry run only shows first iteration estimate

        result.time_seconds = time.time() - start_time
        return result

    def create_pr(
        self,
        title: Optional[str] = None,
        base_branch: str = "main",
    ) -> PRResult:
        """Create a GitHub PR with the applied fixes.

        Workflow:
        1. Run the fix pipeline (scan → fix → test → re-scan)
        2. Create a new branch
        3. Commit changes
        4. Push branch
        5. Create PR via `gh pr create`

        Args:
            title: PR title. Auto-generated if None.
            base_branch: Target branch (default: main).

        Returns:
            PRResult with success status and PR URL.
        """
        from .github import (
            PRResult,
            check_github,
            commit_changes,
            create_branch,
            create_pr,
            format_pr_body,
            get_repo_info,
            push_branch,
        )

        state = check_github(self.repo_root)
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

        result = self.run(
            threshold=40.0,
            run_tests_flag=False,
        )

        if not result.changes_applied:
            return PRResult(
                success=False,
                error="No fixes to apply",
            )

        # Generate branch name
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        branch_name = f"unslop-fix-{timestamp}"

        if not create_branch(self.repo_root, branch_name):
            return PRResult(
                success=False,
                error=f"Failed to create branch {branch_name}",
                branch=branch_name,
            )

        if not commit_changes(
            self.repo_root,
            message=f"unslop: auto-fix AI-generated code patterns",
            author_name=state.username,
        ):
            return PRResult(
                success=False,
                error="Failed to commit changes",
                branch=branch_name,
            )

        if not push_branch(self.repo_root, branch_name):
            return PRResult(
                success=False,
                error="Failed to push branch",
                branch=branch_name,
            )

        # Generate PR title if not provided
        if not title:
            title = f"unslop: auto-fix AI-generated code patterns ({result.changes_applied} changes)"

        # Generate PR body
        body = format_pr_body(
            title=title,
            original_score=result.original_score,
            final_score=result.final_score,
            changes_applied=len(result.changes_applied),
            iterations=len(result.iterations),
            tests_passed=result.tests_passed,
        )

        repo_info = get_repo_info(self.repo_root)

        pr_result = create_pr(
            repo_root=self.repo_root,
            title=title,
            body=body,
            branch_name=branch_name,
            base_branch=base_branch,
        )

        # Store PR URL in result for reporting
        if pr_result.success and pr_result.pr_url:
            result._pr_url = pr_result.pr_url  # type: ignore[attr-defined]

        return pr_result

    def _scan(self) -> UnslopReport:
        """Scan the codebase and return a report."""
        return self._analyzer.analyze_codebase(max_files=500)

    def _apply_fixes(
        self,
        report: UnslopReport,
    ) -> tuple[int, list[FixChange], list[dict]]:
        """Apply safe fixes to the codebase.

        Groups issues by file, applies fixes iteratively (re-detecting after
        each fix to handle line number shifts), and writes modified files
        in-place.

        Args:
            report: Analysis report from _scan().

        Returns:
            Tuple of (fixes_count, changes_list, files_info_list).
        """
        # Filter issues by confidence and severity
        applicable = [
            i for i in report.issues
            if i.confidence >= self.min_confidence
            and i.severity.value in self.severity_filter
            and i.tell in TIER_1_ALWAYS_SAFE | TIER_2_TEST_GATED
        ]

        if not applicable:
            return 0, [], []

        # Group by file
        by_file: dict[Path, list[UnslopIssue]] = {}
        for issue in applicable:
            by_file.setdefault(issue.file_path, []).append(issue)

        # Import detector and fix functions
        from .tells import (
            detect_verbose_comments, fix_verbose_comments,
            detect_todo_artifacts, fix_todo_artifacts,
            detect_debug_artifacts, fix_debug_artifacts,
            detect_empty_error_handling, fix_empty_error_handling,
            detect_dead_code, fix_dead_code,
            detect_dependency_bloat, fix_dependency_bloat,
        )

        fix_map = {
            TellCategory.VERBOSE_COMMENTS: (detect_verbose_comments, fix_verbose_comments),
            TellCategory.TODO_ARTIFACTS: (detect_todo_artifacts, fix_todo_artifacts),
            TellCategory.DEBUG_ARTIFACTS: (detect_debug_artifacts, fix_debug_artifacts),
            TellCategory.EMPTY_ERROR_HANDLING: (detect_empty_error_handling, fix_empty_error_handling),
            TellCategory.DEAD_CODE: (detect_dead_code, fix_dead_code),
            TellCategory.DEPENDENCY_BLOAT: (detect_dependency_bloat, fix_dependency_bloat),
        }

        total_fixes = 0
        all_changes: list[FixChange] = []
        files_info: list[dict] = []

        for file_path, issues in by_file.items():
            try:
                source = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Track which tells have been applied to this file
            applied_tells: set[TellCategory] = set()

            # Apply fixes iteratively — re-detect after each fix to handle
            # line number shifts from previous fixes
            new_source = source
            for tell, (detect_fn, fix_fn) in fix_map.items():
                if tell in applied_tells:
                    continue

                # Detect current issues for this tell category
                current_issues = detect_fn(new_source, file_path)
                current_issues = [
                    i for i in current_issues
                    if i.confidence >= self.min_confidence
                    and i.severity.value in self.severity_filter
                ]

                if not current_issues:
                    continue

                # Apply fix
                new_source = fix_fn(new_source, current_issues)
                total_fixes += len(current_issues)
                applied_tells.add(tell)

                # Record changes
                for issue in current_issues:
                    tier = 1 if tell in TIER_1_ALWAYS_SAFE else 2
                    all_changes.append(FixChange(
                        file_path=str(issue.file_path),
                        line=issue.line,
                        tell=tell,
                        severity=issue.severity,
                        confidence=issue.confidence,
                        tier=tier,
                        action="removed",
                        original=issue.code_snippet,
                        reasoning=issue.suggested_fix,
                        safe_to_revert=True,
                    ))

            if new_source != source:
                file_path.write_text(new_source, encoding="utf-8")

                files_info.append({
                    "file": str(file_path),
                    "changes": total_fixes,
                    "score_impact": 0,
                })

        return total_fixes, all_changes, files_info

    def _count_applicable_fixes(self, report: UnslopReport) -> int:
        """Count how many fixes would be applied without actually applying them.

        Used for dry-run mode.
        """
        return len([
            i for i in report.issues
            if i.confidence >= self.min_confidence
            and i.severity.value in self.severity_filter
            and i.tell in TIER_1_ALWAYS_SAFE | TIER_2_TEST_GATED
        ])


def apply_fixes_to_file(
    file_path: Path,
    issues: list[UnslopIssue],
) -> tuple[str, int]:
    """Apply fixes to a single file and return the new source.

    This is a standalone utility for use by the pipeline or tests.

    Args:
        file_path: Path to the file to fix.
        issues: List of issues to fix (filtered by confidence/severity).

    Returns:
        Tuple of (new_source, fixes_applied_count).
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return source, 0

    # Group by tell category
    by_tell: dict[TellCategory, list[UnslopIssue]] = {}
    for issue in issues:
        by_tell.setdefault(issue.tell, []).append(issue)

    # Import fix functions
    from .tells import (
        fix_verbose_comments,
        fix_todo_artifacts,
        fix_debug_artifacts,
        fix_empty_error_handling,
        fix_dead_code,
        fix_dependency_bloat,
    )

    fix_map = {
        TellCategory.VERBOSE_COMMENTS: fix_verbose_comments,
        TellCategory.TODO_ARTIFACTS: fix_todo_artifacts,
        TellCategory.DEBUG_ARTIFACTS: fix_debug_artifacts,
        TellCategory.EMPTY_ERROR_HANDLING: fix_empty_error_handling,
        TellCategory.DEAD_CODE: fix_dead_code,
        TellCategory.DEPENDENCY_BLOAT: fix_dependency_bloat,
    }

    new_source = source
    fixes_count = 0
    for tell, fix_fn in fix_map.items():
        if tell in by_tell:
            new_source = fix_fn(new_source, by_tell[tell])
            fixes_count += len(by_tell[tell])

    return new_source, fixes_count
