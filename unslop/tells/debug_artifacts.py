"""Detect and fix debug artifacts in production code.

Research source: Git AutoReview — Tell #10: Debug artifacts
"AI leaves debugging artifacts everywhere. console.log statements with PII
in the output, commented-out blocks with TODO markers that were never meant
to ship, debugger keywords that crash production builds."
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


# Debug artifact patterns
DEBUG_PATTERNS = [
    # JavaScript/TypeScript
    (r'console\.(log|debug|info|warn|error|table|trace|dir|dirxml|group|groupEnd|time|timeEnd|assert|count|countReset|profile|profileEnd)\s*\(', 'console_log'),
    (r'\bdebugger\b', 'debugger_statement'),
    # Python
    (r'\bprint\s*\(', 'python_print'),
    # Java/C#
    (r'System\.out\.print', 'java_print'),
    (r'System\.err\.print', 'java_err_print'),
    (r'Console\.WriteLine', 'csharp_write'),
    (r'Console\.Error\.WriteLine', 'csharp_err_write'),
    # General
    (r'//\s*(commented out|disabled|temp|temporary|testing)\s*[:\s]', 'commented_out_code'),
]


def _is_in_docstring(source: str, line_num: int) -> bool:
    """Check if a line is inside a docstring.

    Simple heuristic: track triple-quoted string blocks.
    """
    lines = source.splitlines()
    in_docstring = False
    quote_char = None
    for i in range(line_num):
        line = lines[i]
        stripped = line.strip()
        if not in_docstring:
            if '"""' in stripped or "'''" in stripped:
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_docstring = True
                    quote_char = '"""' if '"""' in stripped else "'''"
        else:
            if quote_char and quote_char in stripped:
                in_docstring = False
                quote_char = None
    return in_docstring


def _is_cli_script(file_path: Path) -> bool:
    """Check if the file is a CLI/benchmark script with intentional print output."""
    name = file_path.name.lower()
    return ('cli' in name or 'cli_' in name or 'main' in name or
            'benchmark' in name or 'script' in name or
            name == '__main__.py')


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect debug artifacts in production code.

    Checks for:
    - console.log statements
    - print() statements
    - debugger statements
    - Commented-out code blocks
    - PII in debug output

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each debug artifact found.
    """
    issues = []
    lines = source.splitlines()

    # Skip CLI/benchmark scripts — they have intentional print output
    if _is_cli_script(file_path):
        return issues

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip lines inside docstrings
        if _is_in_docstring(source, i):
            continue

        for pattern, artifact_type in DEBUG_PATTERNS:
            match = re.search(pattern, line)
            if match:
                severity = Severity.MEDIUM

                if artifact_type in ('console_log', 'python_print') and any(
                    p in line.lower()
                    for p in ('password', 'token', 'secret', 'key', 'api_key', 'ssn', 'email', 'phone', 'credit', 'card')
                ):
                    severity = Severity.HIGH

                issues.append(UnslopIssue(
                    tell=TellCategory.DEBUG_ARTIFACTS,
                    severity=severity,
                    description=f'Debug artifact: "{match.group(0)[:40]}"',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=stripped[:80],
                    suggested_fix='Remove debug statement or convert to proper logging',
                    confidence=0.95,
                    research_source='Git AutoReview — 12-item checklist, Tell #10: Debug artifacts',
                ))
                break  # Only report once per line

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply debug artifact fixes to source code.

    Args:
        source: Original source code.
        issues: List of debug artifact issues to fix.

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

            if re.match(r'(console\.(log|debug|info|warn|error)\s*\(|debugger|print\s*\()', stripped):
                lines_to_remove.add(idx)

            if re.match(r'^(//|#|/\*|\*)\s*(commented out|disabled|temp|temporary|testing)', stripped, re.IGNORECASE):
                lines_to_remove.add(idx)

    # Apply removals
    result = []
    for i, line in enumerate(lines):
        if i not in lines_to_remove:
            result.append(line)

    return ''.join(result)
