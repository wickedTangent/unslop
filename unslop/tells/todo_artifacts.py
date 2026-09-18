"""Detect and fix TODO/FIXME/HACK artifacts in production code.

Research source: Justin McKelvey's "9 Tells" — Tell #6
"TODO and placeholder blocks in production — // TODO: add real authentication
here — live, on the internet, taking user data."

Also: Git AutoReview — Tell #10: Debug artifacts
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


# Patterns for TODO/FIXME/HACK artifacts
TODO_PATTERNS = [
    (r'//\s*(TODO|FIXME|HACK|XXX|BUG|WORKAROUND)[:\s]+', 'comment'),
    (r'#\s*(TODO|FIXME|HACK|XXX|BUG|WORKAROUND)[:\s]+', 'comment'),
    (r'/\*\*\s*(TODO|FIXME|HACK|XXX|BUG|WORKAROUND)[:\s]+', 'block_comment'),
    (r'<!--\s*(TODO|FIXME|HACK|XXX|BUG|WORKAROUND)[:\s]+', 'html_comment'),
]


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect TODO/FIXME/HACK artifacts in production code.

    Checks for:
    - TODO comments in production code
    - FIXME comments
    - HACK comments
    - Placeholder implementations

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each TODO artifact found.
    """
    issues = []
    lines = source.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        for pattern, comment_type in TODO_PATTERNS:
            match = re.search(pattern, stripped, re.IGNORECASE)
            if match:
                keyword = match.group(1).upper()
                # Extract the full comment text
                full_comment = stripped[stripped.find(match.group(0)):]

                severity = Severity.MEDIUM
                if keyword in ('FIXME', 'BUG'):
                    severity = Severity.HIGH
                elif keyword == 'HACK':
                    severity = Severity.MEDIUM

                issues.append(UnslopIssue(
                    tell=TellCategory.TODO_ARTIFACTS,
                    severity=severity,
                    description=f'{keyword} in production code: "{full_comment[:60]}"',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=stripped[:80],
                    suggested_fix=f'Remove {keyword} comment or create a ticket reference',
                    confidence=0.95,
                    research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #6: TODO blocks in production',
                ))
                break  # Only report once per line

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply TODO artifact fixes to source code.

    Args:
        source: Original source code.
        issues: List of TODO issues to fix.

    Returns:
        Fixed source code.
    """
    # Group issues by line
    by_line: dict[int, list[UnslopIssue]] = {}
    for issue in issues:
        if issue.line:
            by_line.setdefault(issue.line, []).append(issue)

    lines = source.splitlines(keepends=True)
    lines_to_remove: set[int] = set()

    for line_num, line_issues in by_line.items():
        idx = line_num - 1
        if idx < 0 or idx >= len(lines):
            continue

        for issue in line_issues:
            stripped = lines[idx].strip()
            if re.match(r'^(//|#|/\*\*|<!--)\s*(TODO|FIXME|HACK|XXX|BUG|WORKAROUND)', stripped, re.IGNORECASE):
                # If it's a standalone comment line, remove it
                lines_to_remove.add(idx)

    # Apply removals
    result = []
    for i, line in enumerate(lines):
        if i not in lines_to_remove:
            result.append(line)

    return ''.join(result)
