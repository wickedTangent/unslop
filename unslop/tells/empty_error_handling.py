"""Detect and fix empty/silent error handling.

Research source: Justin McKelvey's "9 Tells" — Tell #8
"Error handling that swallows everything — beautiful try/catch blocks that
catch every exception and do nothing. It looks defensive. It's actually a blindfold."

Also: Git AutoReview — Tell #5: Error handling completeness
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


def _get_indent(line: str) -> str:
    """Get the indentation of a line."""
    return line[:len(line) - len(line.lstrip())]


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect empty/silent error handling in source code.

    Checks for:
    - except Exception: pass (Python)
    - catch (Exception e) {} (Java/C#)
    - try { ... } catch { } (TypeScript/JS with empty handler)
    - Error handlers that log nothing and return default values

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each empty error handling found.
    """
    issues = []
    lines = source.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Python: except Exception: pass / except: pass
        if re.match(r'except\s+.*:\s*pass\s*$', stripped):
            issues.append(UnslopIssue(
                tell=TellCategory.EMPTY_ERROR_HANDLING,
                severity=Severity.CRITICAL,
                description=f'Empty exception handler: "{stripped}" — swallows all errors silently',
                file_path=file_path,
                line=i + 1,
                code_snippet=stripped,
                suggested_fix='Remove this handler or add specific error handling',
                confidence=0.99,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #8: Error handling that swallows everything',
            ))
            i += 1
            continue

        # Python: except: pass (bare except)
        if stripped == 'except pass' or stripped == 'except: pass':
            issues.append(UnslopIssue(
                tell=TellCategory.EMPTY_ERROR_HANDLING,
                severity=Severity.CRITICAL,
                description=f'Bare except with pass — catches everything silently',
                file_path=file_path,
                line=i + 1,
                code_snippet=stripped,
                suggested_fix='Remove or add specific error handling',
                confidence=0.99,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #8',
            ))
            i += 1
            continue

        # Python: try block with empty except
        if stripped.startswith('try:'):
            indent = _get_indent(line)
            # Look ahead for except block
            j = i + 1
            found_empty_except = False
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()

                # Allow except: at same indent as try: (it's part of the try/except)
                if next_stripped and not next_stripped.startswith('#'):
                    next_indent = _get_indent(next_line)
                    # Only break if we've gone back to the try's indent AND it's not an except
                    if next_indent <= indent and not re.match(r'except\s+.*:', next_stripped):
                        break

                if re.match(r'except\s+.*:', next_stripped):
                    # Check if the except body is empty (only pass or comments)
                    k = j + 1
                    body_lines = []
                    except_indent = _get_indent(next_line)
                    while k < len(lines):
                        body_line = lines[k]
                        body_stripped = body_line.strip()
                        if not body_stripped:
                            k += 1
                            continue
                        if body_stripped.startswith('#'):
                            k += 1
                            continue
                        if _get_indent(body_line) > except_indent:
                            body_lines.append(body_stripped)
                            k += 1
                        else:
                            break

                    if body_lines and all(b in ('pass', '') for b in body_lines):
                        issues.append(UnslopIssue(
                            tell=TellCategory.EMPTY_ERROR_HANDLING,
                            severity=Severity.CRITICAL,
                            description=f'Empty except block at line {j + 1} — catches exceptions silently',
                            file_path=file_path,
                            line=j + 1,
                            code_snippet=f'{next_stripped} -> {body_lines[0] if body_lines else "(empty)"}',
                            suggested_fix='Remove empty except block or add specific error handling',
                            confidence=0.95,
                            research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #8',
                        ))
                        found_empty_except = True
                    break

                j += 1

        # TypeScript/JS: try { ... } catch { } or catch (err) { }
        if stripped.startswith('try {') or stripped == 'try{':
            indent = _get_indent(line)
            # Look for catch block
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()

                if re.match(r'catch\s*\(', next_stripped):
                    # Check if catch body is empty
                    k = j + 1
                    body_lines = []
                    while k < len(lines):
                        body_stripped = lines[k].strip()
                        if not body_stripped:
                            k += 1
                            continue
                        if body_stripped == '}':
                            break
                        body_lines.append(body_stripped)
                        k += 1

                    if not body_lines or all(b in ('', '//', '/*', '*/') for b in body_lines):
                        issues.append(UnslopIssue(
                            tell=TellCategory.EMPTY_ERROR_HANDLING,
                            severity=Severity.CRITICAL,
                            description=f'Empty catch block at line {j + 1} — swallows errors silently',
                            file_path=file_path,
                            line=j + 1,
                            code_snippet=next_stripped[:60],
                            suggested_fix='Remove empty catch block or add error handling',
                            confidence=0.95,
                            research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #8',
                        ))
                    break

                j += 1

        if re.search(r'return\s+(None|false|0|\{\}|\[\]|""|\'\')\s*$', stripped):
            # Check if this is inside an error handler context
            # Look backwards for try/catch/except
            context_start = max(0, i - 10)
            context = '\n'.join(lines[context_start:i])
            if 'except' in context.lower() or 'catch' in context.lower() or 'error' in context.lower():
                issues.append(UnslopIssue(
                    tell=TellCategory.EMPTY_ERROR_HANDLING,
                    severity=Severity.HIGH,
                    description=f'Returning default value in error handler — masks errors',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=stripped[:60],
                    suggested_fix='Propagate the error or return a meaningful error object',
                    confidence=0.7,
                    research_source='Git AutoReview — 12-item checklist, Tell #5: Error handling completeness',
                ))

        i += 1

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply error handling fixes to source code.

    For empty except/catch blocks, replaces them with 'raise' to propagate
    the error instead of silently swallowing it. This avoids leaving the
    try block without a handler (which would cause a SyntaxError).

    Args:
        source: Original source code.
        issues: List of error handling issues to fix.

    Returns:
        Fixed source code.
    """
    lines = source.splitlines(keepends=True)

    # Group issues by line
    by_line: dict[int, list[UnslopIssue]] = {}
    for issue in issues:
        if issue.line:
            by_line.setdefault(issue.line, []).append(issue)

    # Track lines to remove (empty except/catch blocks)
    lines_to_remove: set[int] = set()
    # Track lines to replace with 'raise'
    lines_to_replace: dict[int, str] = {}

    for line_num, line_issues in by_line.items():
        idx = line_num - 1
        if idx < 0 or idx >= len(lines):
            continue

        for issue in line_issues:
            stripped = lines[idx].strip()

            # Handle "except X: pass" on single line
            if re.match(r'except\s+.*:\s*pass\s*$', stripped):
                # Replace with 'raise' to propagate the error
                lines_to_replace[idx] = stripped.replace('pass', 'raise')
                continue

            # Handle multi-line empty except blocks
            if re.match(r'except\s+.*:', stripped):
                # Check if next non-empty line is "pass"
                j = idx + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip() == 'pass':
                    # Replace the pass line with 'raise' at SAME indent as pass
                    pass_indent = _get_indent(lines[j])
                    lines_to_replace[j] = pass_indent + 'raise\n'

    # Apply changes
    result = []
    for i, line in enumerate(lines):
        if i in lines_to_remove:
            continue
        if i in lines_to_replace:
            result.append(lines_to_replace[i])
        else:
            result.append(line)

    return ''.join(result)
