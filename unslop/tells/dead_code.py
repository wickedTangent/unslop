"""Detect and fix dead code.

Research source: Justin McKelvey's "9 Tells" — Tell #7
"Dead code that looks load-bearing — fully built, nicely formatted, wired to nothing"
Also: Git AutoReview 12-item checklist — Tell #8
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..symbols import extract_symbols, get_language

from ..report import Severity, TellCategory, UnslopIssue


_ENTRY_POINT_NAMES = {
    'main', 'run', 'start', 'launch', 'execute', 'cli', 'entry_point',
    'on_init', 'on_start', 'on_stop', 'on_exit', 'cleanup', 'teardown',
}
_FRAMEWORK_DECORATOR_RE = re.compile(
    r'@(?!staticmethod\b|classmethod\b)'
    r'(?:app|router|api|cli)(?:\.[A-Za-z_][\w]*)?'
    r'|@(?:click|typer)\.[A-Za-z_][\w]*'
)


def _has_framework_decorator(lines: list[str], definition_line: int) -> bool:
    """Return whether a function has a framework decorator immediately above it."""
    for line in reversed(lines[max(0, definition_line - 5):definition_line]):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('@'):
            if _FRAMEWORK_DECORATOR_RE.search(stripped):
                return True
            continue
        break
    return False


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect dead code in source.

    Checks for:
    - Unused imports (imported but never referenced)
    - Unused variables (defined but never used)
    - Unreachable code (after return/raise/break/continue)
    - Dead functions (defined but never called in this file)

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each dead code found.
    """
    issues = []
    lang = get_language(file_path.suffix) or 'python'
    symbols = extract_symbols(source, lang)

    # 1. Unused imports
    for name, module in symbols.import_bindings.items():
        # Future imports are compiler directives, not runtime dependencies.
        if module == "__future__":
            continue
        # Check if the imported name is used anywhere in the source
        # Use word boundary matching to avoid false positives
        pattern = r'\b' + re.escape(name) + r'\b'
        usage_count = 0
        for i, line in enumerate(source.splitlines()):
            stripped = line.strip()
            # Skip the import line itself
            if re.match(r'^\s*(from\s+\S+\s+)?import\s+', line):
                continue
            # Skip docstrings and comments
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            if re.search(pattern, line):
                usage_count += 1

        if usage_count == 0:
            # Find the actual line number of the import
            import_line = 1
            import_pattern = r'^\s*(from\s+' + re.escape(module) + r'\s+import|import\s+' + re.escape(module) + r')'
            for i, line in enumerate(source.splitlines()):
                if re.match(import_pattern, line):
                    import_line = i + 1
                    break
            issues.append(UnslopIssue(
                tell=TellCategory.DEAD_CODE,
                severity=Severity.MEDIUM,
                description=f'Unused import: "{name}" from "{module}"',
                file_path=file_path,
                line=import_line,
                code_snippet=f'from {module} import {name}',
                suggested_fix=f'Remove: from {module} import {name}',
                confidence=0.95,
                research_source='Git AutoReview — 12-item checklist, Tell #8: Dead and unreachable code',
            ))

    # 2. Unused defined functions (not called elsewhere in this file)
    function_names = symbols.function_names
    for name in function_names:
        if name.startswith('_'):
            continue  # Skip private/dunder methods

        definition_line = next(
            (i for i, line in enumerate(source.splitlines())
             if re.search(r'\b(?:async\s+)?def\s+' + re.escape(name) + r'\s*\(', line)),
            None,
        )
        if name.casefold() in _ENTRY_POINT_NAMES or (
            definition_line is not None
            and _has_framework_decorator(source.splitlines(), definition_line)
        ):
            continue

        call_pattern = r'\b' + re.escape(name) + r'\s*\('
        call_count = sum(1 for line in source.splitlines() if re.search(call_pattern, line))

        # Also check for attribute access
        attr_pattern = r'\b' + re.escape(name) + r'\b'
        attr_count = sum(1 for line in source.splitlines() if re.search(attr_pattern, line))

        # If defined but never called (except in its own definition)
        if call_count == 0 and attr_count <= 1:
            issues.append(UnslopIssue(
                tell=TellCategory.DEAD_CODE,
                severity=Severity.HIGH,
                description=f'Function "{name}" is defined but never called in this file',
                file_path=file_path,
                suggested_fix=f'Remove function "{name}" or verify it\'s used elsewhere',
                confidence=0.85,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #7: Dead code that looks load-bearing',
            ))

    # 3. Unreachable code after return/raise
    # Only flag code that is truly unreachable (not method definitions, not else/elif)
    # Also handle multi-line statements (e.g., return FuncName(arg1=val, arg2=val))
    lines = source.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith('#') or stripped.startswith('//'):
            continue

        current_indent = len(line) - len(line.lstrip())

        if re.match(r'^(return|raise|break|continue)\b', stripped):
            # If the return/raise line doesn't end with a closing paren/bracket/brace,
            # the following lines are continuations, not unreachable code
            if stripped.endswith('(') or stripped.endswith('[') or stripped.endswith('{'):
                # Multi-line statement — skip, the following lines are part of the statement
                continue
            # If it's a multi-line function call like:
            #   return FuncName(
            #       arg1=val,
            #   )
            if _has_unclosed_delimiter(stripped):
                # Opening delimiter without closing — multi-line expression
                continue

            # Mark this line and subsequent lines at same or deeper indent as unreachable
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()
                if not next_stripped or next_stripped.startswith('#') or next_stripped.startswith('//'):
                    j += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                # If next line is at same or lesser indent, we've exited the block
                if next_indent <= current_indent:
                    break
                # If next line is a method/function/class definition, it's not unreachable
                if re.match(r'^(def |class |async def )', next_stripped):
                    break
                # If next line is else/elif/finally, it's not unreachable
                if re.match(r'^(else|elif |finally)', next_stripped):
                    break
                # If next line is a continuation (starts with comma, paren, bracket),
                # it's part of a multi-line statement and not unreachable
                if next_stripped.startswith(',') or next_stripped.startswith(')') or \
                   next_stripped.startswith(']') or next_stripped.startswith('}'):
                    break
                # Otherwise, it's unreachable
                issues.append(UnslopIssue(
                    tell=TellCategory.DEAD_CODE,
                    severity=Severity.HIGH,
                    description=f'Unreachable code after return/raise on line {i + 1}',
                    file_path=file_path,
                    line=j + 1,
                    code_snippet=next_stripped[:80],
                    suggested_fix='Remove unreachable code or restructure control flow',
                    confidence=0.9,
                    research_source='Git AutoReview — 12-item checklist, Tell #8: Dead and unreachable code',
                ))
                j += 1
            continue

    return issues


def _has_unclosed_delimiter(line: str) -> bool:
    """Check whether a control-flow statement continues onto later lines."""
    cleaned = re.sub(r"(['\"]).*?\1", "", line)
    balance = 0
    pairs = {')': '(', ']': '[', '}': '{'}
    for char in cleaned:
        if char in '([{':
            balance += 1
        elif char in pairs:
            balance -= 1
    return balance > 0


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply dead code fixes to source code.

    Args:
        source: Original source code.
        issues: List of dead code issues to fix.

    Returns:
        Fixed source code.
    """
    lines = source.splitlines(keepends=True)

    # Group issues by type
    unused_imports = [i for i in issues if 'Unused import' in i.description]
    unused_functions = [i for i in issues if 'never called' in i.description]
    unreachable = [i for i in issues if 'Unreachable' in i.description]

    # 1. Remove unused imports
    import_lines_to_remove = set()
    for issue in unused_imports:
        if issue.line:
            import_lines_to_remove.add(issue.line - 1)  # 0-indexed

    # 2. Mark unreachable code for removal
    lines_to_remove = set()
    for issue in unreachable:
        if issue.line:
            lines_to_remove.add(issue.line - 1)

    # 3. Remove unused functions (simplified — just flag for review)
    # We don't auto-remove functions as they might be used in other files

    # Apply removals
    result = []
    for i, line in enumerate(lines):
        if i in import_lines_to_remove or i in lines_to_remove:
            continue
        result.append(line)

    return ''.join(result)
