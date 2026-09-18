"""Detect and fix dependency bloat.

Research source: Justin McKelvey's "9 Tells" — Tell #3
"Dependency bloat — Packages imported and never called. Libraries pinned in the
manifest that nothing uses. Three tools doing one job."

Also: Git AutoReview — Tell #2: Hallucinated packages
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ..symbols import extract_symbols, get_language

from ..pattern_index import PatternIndex
from ..report import Severity, TellCategory, UnslopIssue


_SIDE_EFFECT_MODULES = {
    'matplotlib.pyplot', 'tkinter', 'tkinter.ttk', 'pygame',
    'pygame.locals', 'wx', 'gtk', 'qt',
}


def _type_checking_import_lines(source: str) -> set[int]:
    """Return import line numbers guarded by ``if TYPE_CHECKING``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_type_checking = (
            isinstance(test, ast.Name) and test.id == 'TYPE_CHECKING'
        ) or (
            isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING'
        )
        if not is_type_checking:
            continue
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                lines.add(child.lineno)
    return lines


def _is_side_effect_import(name: str, module: str) -> bool:
    """Recognize imports commonly retained for module initialization effects."""
    return name.casefold() in _SIDE_EFFECT_MODULES or module.casefold() in _SIDE_EFFECT_MODULES


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect dependency bloat in source code.

    Checks for:
    - Imported modules with zero call sites
    - New dependencies that duplicate existing ones
    - Multiple packages serving the same purpose

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex with existing codebase patterns.

    Returns:
        List of UnslopIssue for each dependency bloat found.
    """
    issues = []
    lang = get_language(file_path.suffix) or 'python'
    symbols = extract_symbols(source, lang)
    type_checking_lines = _type_checking_import_lines(source)

    # 1. Unused imports from 'from X import Y' statements (via extract_symbols)
    for name, module in symbols.import_bindings.items():
        if module == "__future__":
            continue
        import_line = next(
            (i + 1 for i, line in enumerate(source.splitlines())
             if re.search(r'\b' + re.escape(name) + r'\b', line)
             and 'import' in line),
            None,
        )
        if import_line in type_checking_lines or _is_side_effect_import(name, module):
            continue
        # Check if the imported name is used anywhere in the source
        pattern = r'\b' + re.escape(name) + r'\b'
        usage_count = 0
        for i, line in enumerate(source.splitlines()):
            if 'import' in line.lower():
                continue
            if re.search(pattern, line):
                usage_count += 1

        if usage_count == 0:
            issues.append(UnslopIssue(
                tell=TellCategory.DEPENDENCY_BLOAT,
                severity=Severity.MEDIUM,
                description=f'Unused import: "{name}" from "{module}"',
                file_path=file_path,
                line=1,
                code_snippet=f'from {module} import {name}',
                suggested_fix=f'Remove: from {module} import {name}',
                confidence=0.95,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #3: Dependency bloat',
            ))

    # 2. Unused bare imports (import X, import X as Y)
    # extract_symbols doesn't catch these, so we do a regex-based check
    bare_import_pattern = re.compile(r'^\s*import\s+([\w.]+)(?:\s+as\s+(\w+))?\s*$')
    for i, line in enumerate(source.splitlines()):
        match = bare_import_pattern.match(line)
        if match:
            module = match.group(1)
            alias = match.group(2) or module.split('.')[-1]
            if _is_side_effect_import(alias, module):
                continue
            # Check if the alias is used anywhere in the source (excluding import lines)
            pattern = r'\b' + re.escape(alias) + r'\b'
            usage_count = 0
            for j, other_line in enumerate(source.splitlines()):
                if 'import' in other_line.lower():
                    continue
                if re.search(pattern, other_line):
                    usage_count += 1

            if usage_count == 0:
                issues.append(UnslopIssue(
                    tell=TellCategory.DEPENDENCY_BLOAT,
                    severity=Severity.MEDIUM,
                    description=f'Unused import: "{alias}" from "{module}"',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=line.strip(),
                    suggested_fix=f'Remove: {line.strip()}',
                    confidence=0.95,
                    research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #3: Dependency bloat',
                ))

    # 2. Check for duplicate-purpose imports (if context is available)
    if context and 'pattern_index' in context:
        pattern_index: Optional[PatternIndex] = context['pattern_index']
        if pattern_index:
            for module in symbols.imported_modules:
                for purpose, existing_modules in pattern_index.import_purposes.items():
                    if module in existing_modules:
                        # that serves the same purpose
                        for name, imp_module in symbols.import_bindings.items():
                            if imp_module in existing_modules and imp_module != module:
                                issues.append(UnslopIssue(
                                    tell=TellCategory.DEPENDENCY_BLOAT,
                                    severity=Severity.HIGH,
                                    description=f'Duplicate-purpose import: "{module}" serves same purpose as "{imp_module}" ({purpose})',
                                    file_path=file_path,
                                    suggested_fix=f'Use existing "{imp_module}" instead of "{module}"',
                                    confidence=0.8,
                                    research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #3: Three tools doing one job',
                                ))

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply dependency bloat fixes to source code.

    Removes unused import lines (both 'from X import Y' and 'import X').
    Handles multi-import lines by removing only the unused names.

    Args:
        source: Original source code.
        issues: List of dependency bloat issues to fix.

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
    # Track names to remove from multi-import lines
    multi_import_removals: dict[int, list[str]] = {}

    for line_num, line_issues in by_line.items():
        idx = line_num - 1
        if idx < 0 or idx >= len(lines):
            continue

        line = lines[idx]
        stripped = line.strip()

        from_import_match = re.match(
            r'^(\s*from\s+\S+\s+import\s+)(.+)$',
            stripped
        )
        if from_import_match:
            prefix = from_import_match.group(1)
            names_str = from_import_match.group(2)
            # Parse the imported names (handles commas, parens, etc.)
            names = [n.strip().split(' as ')[-1].strip() for n in names_str.replace('(', '').replace(')', '').split(',') if n.strip()]
            unused_names = [issue.code_snippet.split('"')[1] if '"' in issue.code_snippet else '' for issue in line_issues]
            unused_names = [n for n in unused_names if n]

            remaining_names = [n for n in names if n not in unused_names]

            if not remaining_names:
                # All names unused — remove the entire line
                lines_to_remove.add(idx)
            else:
                # Some names remain — replace the import line
                new_import = prefix + ', '.join(remaining_names)
                lines[idx] = new_import + '\n' if not line.endswith('\n') else new_import

            continue

        bare_import_match = re.match(r'^\s*import\s+', stripped)
        if bare_import_match:
            lines_to_remove.add(idx)
            continue

        if stripped.startswith('from ') and 'import' in stripped:
            lines_to_remove.add(idx)

    # Apply removals
    result = []
    for i, line in enumerate(lines):
        if i not in lines_to_remove:
            result.append(line)

    return ''.join(result)
