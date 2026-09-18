"""CLI entry point for unslop.

Usage:
    unslop /path/to/file.py              # Scan a single file
    unslop /path/to/repo --codebase       # Scan entire codebase
    unslop fix /path/to/repo              # Run fix pipeline
    unslop fix /path/to/repo --dry-run    # Preview fixes without applying
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .analyzer import UnslopAnalyzer
from .fix_pipeline import FixPipeline
from .report import UnslopReport


def cmd_scan(args: argparse.Namespace) -> int:
    """Handle the scan command (default behavior)."""
    repo_root = Path(args.path).resolve()

    analyzer = UnslopAnalyzer(repo_root=repo_root, max_index_files=args.max_files)

    if args.codebase:
        report = analyzer.analyze_codebase(max_files=args.max_files)
    else:
        file_path = Path(args.path)
        if not file_path.is_file():
            print(f"Error: {file_path} is not a file", file=sys.stderr)
            return 2
        report = analyzer.analyze_file(file_path)

    # Output both reports by default
    written = []

    if not args.no_markdown:
        md_path = Path(args.report)
        md_path.write_text(report.to_markdown(), encoding="utf-8")
        written.append(f"Markdown: {md_path}")

    if not args.no_json:
        json_path = Path(args.json_report)
        json_report = report.to_json()
        json_report["timestamp"] = datetime.now(timezone.utc).isoformat()
        json_path.write_text(json.dumps(json_report, indent=2) + "\n", encoding="utf-8")
        written.append(f"JSON: {json_path}")

    if written:
        print("\nReports written:")
        for w in written:
            print(f"  {w}")

    print("\n" + analyzer.report_summary(report))
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    """Handle the fix command."""
    repo_path = Path(args.repo).resolve()
    # If a file is given, use its parent directory
    if repo_path.is_file():
        repo_path = repo_path.parent.resolve()
    repo_root = repo_path

    pipeline = FixPipeline(
        repo_root=repo_root,
        min_confidence=args.min_confidence / 100.0,
        max_iterations=args.max_iterations,
        severity_filter=args.severity.split(",") if args.severity else None,
    )

    if args.create_pr:
        result = pipeline.create_pr(
            title=args.pr_title,
            base_branch=args.pr_base,
        )
        print(f"\n{result}")
        if result.success:
            return 0
        return 1

    if args.dry_run:
        result = pipeline.run_dry(threshold=args.threshold)
    else:
        result = pipeline.run(
            threshold=args.threshold,
            run_tests_flag=args.run_tests,
            test_cmd=args.test_cmd,
            test_timeout=args.test_timeout,
        )

    # Write reports
    if not args.no_markdown:
        md_path = Path(args.report)
        md_path.write_text(result.to_markdown(), encoding="utf-8")
        print(f"Markdown report: {md_path}")

    if not args.no_json:
        json_path = Path(args.json_report)
        json_path.write_text(
            json.dumps(result.to_json(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report: {json_path}")

    print(f"\n{result}")

    # Exit codes
    if result.stopped_reason == "dirty_working_tree":
        return 2
    if result.stopped_reason == "not_a_git_repo":
        return 2
    if result.stopped_reason == "tests_failed":
        return 1
    if result.stopped_reason == "max_iterations":
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unslop — Polish AI-generated code to human quality",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- scan command (default) ---
    scan_parser = subparsers.add_parser(
        "scan",
        help="Analyze code for AI-generated patterns (read-only)",
        aliases=["", "file"],  # Empty string = default when no subcmd given
    )
    scan_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="File or directory to analyze (default: current directory)",
    )
    scan_parser.add_argument(
        "--codebase",
        action="store_true",
        help="Analyze the entire codebase (quality exercise)",
    )
    scan_parser.add_argument(
        "--max-files",
        type=int,
        default=500,
        help="Maximum files to analyze in codebase mode (default: 500)",
    )
    scan_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed issue information",
    )
    scan_parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip writing the Markdown report",
    )
    scan_parser.add_argument(
        "--no-json",
        action="store_true",
        help="Skip writing the JSON report",
    )
    scan_parser.add_argument(
        "--report",
        type=str,
        default="unslopped.md",
        help="Markdown report path (default: unslopped.md)",
    )
    scan_parser.add_argument(
        "--json-report",
        type=str,
        default="unslopped.json",
        help="JSON report path (default: unslopped.json)",
    )

    # --- fix command ---
    fix_parser = subparsers.add_parser(
        "fix",
        help="Iteratively fix AI-generated code patterns (test-gated)",
    )
    fix_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to repository root",
    )
    fix_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without applying",
    )
    fix_parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run test suite after each fix iteration",
    )
    fix_parser.add_argument(
        "--test-cmd",
        type=str,
        default=None,
        help="Custom test command (auto-detected if not specified)",
    )
    fix_parser.add_argument(
        "--test-timeout",
        type=int,
        default=120,
        help="Test command timeout in seconds (default: 120)",
    )
    fix_parser.add_argument(
        "--threshold",
        type=float,
        default=40.0,
        help="Target score to reach (lower is better, default: 40)",
    )
    fix_parser.add_argument(
        "--min-confidence",
        type=float,
        default=80,
        help="Minimum confidence %% to apply a fix (default: 80)",
    )
    fix_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum scan→fix→test loop iterations (default: 10)",
    )
    fix_parser.add_argument(
        "--severity",
        type=str,
        default=None,
        help="Comma-separated severity levels to fix (default: all)",
    )
    fix_parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip writing the Markdown report",
    )
    fix_parser.add_argument(
        "--no-json",
        action="store_true",
        help="Skip writing the JSON report",
    )
    fix_parser.add_argument(
        "--report",
        type=str,
        default="unslopped.md",
        help="Markdown report path (default: unslopped.md)",
    )
    fix_parser.add_argument(
        "--json-report",
        type=str,
        default="unslopped.json",
        help="JSON report path (default: unslopped.json)",
    )
    fix_parser.add_argument(
        "--create-pr",
        action="store_true",
        help="Create a GitHub PR with the fixes",
    )
    fix_parser.add_argument(
        "--pr-title",
        type=str,
        default=None,
        help="PR title (auto-generated if not specified)",
    )
    fix_parser.add_argument(
        "--pr-base",
        type=str,
        default="main",
        help="Target branch for PR (default: main)",
    )

    try:
        args = parser.parse_args()
    except SystemExit as e:
        # argparse calls sys.exit(0) on --help, sys.exit(2) on error
        sys.exit(e.code if e.code is not None else 0)

    # Handle empty command (default to scan)
    if args.command is None or args.command == "":
        args.command = "scan"
        # If no subcommand was given, argparse didn't populate scan_parser args
        if not hasattr(args, "path"):
            args.path = "."
        if not hasattr(args, "codebase"):
            args.codebase = False
        if not hasattr(args, "max_files"):
            args.max_files = 500
        if not hasattr(args, "verbose"):
            args.verbose = False
        if not hasattr(args, "no_markdown"):
            args.no_markdown = False
        if not hasattr(args, "no_json"):
            args.no_json = False
        if not hasattr(args, "report"):
            args.report = "unslopped.md"
        if not hasattr(args, "json_report"):
            args.json_report = "unslopped.json"

    if args.command == "scan":
        exit_code = cmd_scan(args)
    elif args.command == "fix":
        exit_code = cmd_fix(args)
    else:
        parser.print_help()
        exit_code = 2

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
