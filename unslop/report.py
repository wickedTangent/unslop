"""Report data structures for unslop analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TellCategory(str, Enum):
    """Category of AI-generated code tell."""
    GENERIC_NAMING = "generic_naming"           # Tell 4: data2, handleClick3
    VERBOSE_COMMENTS = "verbose_comments"        # Tell 1: comments explaining the obvious
    DEAD_CODE = "dead_code"                      # Tell 7: dead code that looks load-bearing
    EMPTY_ERROR_HANDLING = "empty_error_handling" # Tell 8: except: pass
    TODO_ARTIFACTS = "todo_artifacts"            # Tell 6: TODO blocks in production
    DEBUG_ARTIFACTS = "debug_artifacts"          # Tell 10: console.log, print
    DEPENDENCY_BLOAT = "dependency_bloat"        # Tell 3: unused imports
    PATTERN_INCONSISTENCY = "pattern_inconsistency" # Tell 2: same problem solved 5 ways
    TEST_QUALITY = "test_quality"                # Tell 5: tests that don't test
    GLOBAL_INCOHERENCE = "global_incoherence"    # Tell 9: locally valid, globally incoherent
    SECURITY_VULNERABILITY = "security_vulnerability"  # Tell 10: SQLi, secrets, XSS
    VOLUME_ANOMALY = "volume_anomaly"            # Tell 11: functions/files too large
    CROSS_FILE_INCOHERENCE = "cross_file_coherence"    # Tell 2: broken cross-file references


@dataclass
class UnslopIssue:
    """A single issue found in the code."""
    tell: TellCategory
    severity: Severity
    description: str
    file_path: Path
    line: Optional[int] = None
    column: Optional[int] = None
    code_snippet: Optional[str] = None
    suggested_fix: Optional[str] = None
    confidence: float = 1.0  # 0-1 how confident we are
    research_source: Optional[str] = None  # Which research cited this tell


@dataclass
class UnslopReport:
    """Complete analysis report for a file or codebase."""
    file_path: Optional[Path] = None
    issues: list[UnslopIssue] = field(default_factory=list)
    slop_score: float = 0.0
    total_lines: int = 0
    changed_lines: int = 0
    repo_patterns: Optional[dict] = None  # PatternIndex snapshot

    def add_issue(self, issue: UnslopIssue) -> None:
        self.issues.append(issue)

    def summary(self) -> str:
        """Human-readable summary of the report."""
        lines = []
        if self.file_path:
            lines.append(f"File: {self.file_path}")
        lines.append(f"Slop Score: {self.slop_score:.0f}/100")

        if self.issues:
            lines.append(f"\nIssues Found: {len(self.issues)}")
            # Group by tell category
            by_tell: dict[TellCategory, list[UnslopIssue]] = {}
            for issue in self.issues:
                by_tell.setdefault(issue.tell, []).append(issue)

            for tell, issues in sorted(by_tell.items(), key=lambda x: -len(x[1])):
                lines.append(f"  {tell.value}: {len(issues)} issue(s)")
        else:
            lines.append("\nNo issues found. Code looks clean.")

        return "\n".join(lines)

    def severity_counts(self) -> dict[Severity, int]:
        """Count issues by severity."""
        counts: dict[Severity, int] = {s: 0 for s in Severity}
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts

    def to_markdown(self) -> str:
        """Generate a human-readable Markdown report."""
        lines = []
        lines.append("# Unslop Report\n")

        # Summary
        if self.file_path:
            lines.append(f"**File:** `{self.file_path}`\n")
        else:
            lines.append("**Repository:** codebase-wide analysis\n")

        score_label = (
            "Clean" if self.slop_score < 20 else
            "Mostly clean" if self.slop_score < 40 else
            "Mixed" if self.slop_score < 60 else
            "AI-looking" if self.slop_score < 80 else
            "Slop"
        )
        lines.append(f"**Slop Score:** {self.slop_score:.0f}/100 — {score_label}\n")

        if self.total_lines:
            lines.append(f"**Lines:** {self.total_lines}\n")

        # Severity breakdown
        counts = self.severity_counts()
        lines.append("## Severity Breakdown\n")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            if counts[sev] > 0:
                icon = {Severity.CRITICAL: "🔴", Severity.HIGH: "🟠", Severity.MEDIUM: "🟡", Severity.LOW: "🟢"}[sev]
                lines.append(f"| {icon} {sev.value} | {counts[sev]} |")
        lines.append("")

        # Issues grouped by tell
        if self.issues:
            by_tell: dict[TellCategory, list[UnslopIssue]] = {}
            for issue in self.issues:
                by_tell.setdefault(issue.tell, []).append(issue)

            lines.append("## Issues\n")
            lines.append(f"**Total:** {len(self.issues)} issue(s)\n")

            for tell in sorted(by_tell.keys(), key=lambda t: -len(by_tell[t])):
                issues = by_tell[tell]
                lines.append(f"### {tell.value} ({len(issues)} issue{'s' if len(issues) > 1 else ''})\n")

                for issue in issues:
                    location = f"line {issue.line}" if issue.line else str(issue.file_path)
                    lines.append(f"- **{location}** — {issue.description}")
                    if issue.code_snippet:
                        lang = "py" if issue.file_path.suffix == ".py" else "ts"
                        lines.append(f"  ```{lang}\n  {issue.code_snippet}\n  ```")
                    if issue.suggested_fix:
                        lines.append(f"  - **Suggested fix:** {issue.suggested_fix}")
                    if issue.confidence < 1.0:
                        lines.append(f"  - **Confidence:** {issue.confidence:.0%}")
                    lines.append("")
        else:
            lines.append("## Results\n")
            lines.append("✅ No issues found. Code looks clean.\n")

        return "\n".join(lines)

    def to_json(self) -> dict:
        """Generate a structured JSON-serializable report."""
        counts = self.severity_counts()
        by_tell: dict[TellCategory, list[UnslopIssue]] = {}
        for issue in self.issues:
            by_tell.setdefault(issue.tell, []).append(issue)

        return {
            "version": "1.0",
            "file_path": str(self.file_path) if self.file_path else None,
            "slop_score": round(self.slop_score, 1),
            "total_lines": self.total_lines,
            "severity_counts": {s.value: c for s, c in counts.items() if c > 0},
            "issues": [
                {
                    "tell": issue.tell.value,
                    "severity": issue.severity.value,
                    "description": issue.description,
                    "file_path": str(issue.file_path),
                    "line": issue.line,
                    "column": issue.column,
                    "code_snippet": issue.code_snippet,
                    "suggested_fix": issue.suggested_fix,
                    "confidence": round(issue.confidence, 2),
                    "research_source": issue.research_source,
                }
                for issue in self.issues
            ],
            "by_tell": {
                tell.value: {
                    "count": len(issues),
                    "severity_counts": {
                        s.value: sum(1 for i in issues if i.severity == s)
                        for s in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
                    },
                    "issues": [
                        {
                            "line": issue.line,
                            "description": issue.description,
                            "confidence": round(issue.confidence, 2),
                        }
                        for issue in issues
                    ],
                }
                for tell, issues in by_tell.items()
            },
        }
