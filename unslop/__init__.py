"""Unslop — Polish AI-generated code to human quality.

Public API:

    # Scan
    from unslop import UnslopAnalyzer
    analyzer = UnslopAnalyzer(repo_root="/path/to/repo")
    report = analyzer.analyze_file("/path/to/repo/file.py")
    print(report.to_markdown())

    # Fix
    from unslop import FixPipeline
    pipeline = FixPipeline(repo_root="/path/to/repo")
    result = pipeline.run(threshold=40, run_tests=True)
    print(f"Score: {result.original_score} → {result.final_score}")
    result.write_report("unslopped.md", "unslopped.json")
"""

from __future__ import annotations

from .analyzer import UnslopAnalyzer
from .fix_pipeline import FixPipeline, FixResult, FixIteration, FixChange
from .report import Severity, TellCategory, UnslopIssue, UnslopReport
from .pattern_index import PatternIndex
from .test_runner import TestResult, run_tests, detect_test_command
from .github import (
    GitHubState,
    PRResult,
    CommentResult,
    check_github,
    create_pr,
    post_comment,
    format_pr_body,
)

__all__ = [
    "UnslopAnalyzer",
    "UnslopReport",
    "UnslopIssue",
    "Severity",
    "TellCategory",
    "PatternIndex",
    "FixPipeline",
    "FixResult",
    "FixIteration",
    "FixChange",
    "TestResult",
    "run_tests",
    "detect_test_command",
    "GitHubState",
    "PRResult",
    "CommentResult",
    "check_github",
    "create_pr",
    "post_comment",
    "format_pr_body",
]
__version__ = "0.1.0"
