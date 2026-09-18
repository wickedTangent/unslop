"""Detect and fix pattern inconsistency.

Research source: Justin McKelvey's "9 Tells" — Tell #2
"The same problem solved five different ways — Three HTTP clients. Two date
libraries. Four patterns for form validation. Each prompt session picked its
own favorite, and nobody was watching the whole."

Also: Git AutoReview — Tell #12: Architectural fit
"AI writes code that works in isolation. It does not know that your team made
a deliberate choice to route all DB access through a service layer."
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..symbols import extract_symbols, get_language

from ..pattern_index import PatternIndex
from ..report import Severity, TellCategory, UnslopIssue


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect pattern inconsistency in source code.

    Checks for:
    - Error handling patterns that don't match existing patterns
    - Import patterns that duplicate existing ones
    - Naming that doesn't match the file's convention
    - Architectural patterns that don't fit the project

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex with existing codebase patterns.

    Returns:
        List of UnslopIssue for each pattern inconsistency found.
    """
    issues = []
    lang = get_language(file_path.suffix) or 'python'
    symbols = extract_symbols(source, lang)

    if not context or 'pattern_index' not in context:
        return issues

    pattern_index: PatternIndex = context['pattern_index']

    # A one- or two-file index cannot establish a project convention. Avoid
    # turning a new file into an inconsistency report until there is evidence.
    if pattern_index.total_files_indexed < 3:
        return issues

    # 1. Error handling pattern inconsistency
    existing_error_classes = {e.error_class for e in pattern_index.error_classes}

    for match in re.finditer(
        r'class\s+(\w+Error|\w+Exception)\s*\(\s*(\w+)?\s*\)',
        source
    ):
        error_class = match.group(1)
        if error_class not in existing_error_classes:
            issues.append(UnslopIssue(
                tell=TellCategory.PATTERN_INCONSISTENCY,
                severity=Severity.HIGH,
                description=f'New error class "{error_class}" — codebase uses existing error patterns',
                file_path=file_path,
                suggested_fix=f'Use existing error class or align with {list(existing_error_classes)[0] if existing_error_classes else "project convention"}',
                confidence=0.85,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #2: Same problem solved five different ways',
            ))

    # 2. Import pattern inconsistency
    for module in symbols.imported_modules:
        for purpose, existing_modules in pattern_index.import_purposes.items():
            if module in existing_modules:
                # This module is already used for this purpose — check if there's
                # a duplicate import for the same purpose in this file
                for name, imp_module in symbols.import_bindings.items():
                    if imp_module in existing_modules and imp_module != module:
                        issues.append(UnslopIssue(
                            tell=TellCategory.PATTERN_INCONSISTENCY,
                            severity=Severity.HIGH,
                            description=f'Duplicate import: both "{module}" and "{imp_module}" serve "{purpose}"',
                            file_path=file_path,
                            suggested_fix=f'Use existing "{imp_module}" instead of "{module}"',
                            confidence=0.8,
                            research_source='Git AutoReview — 12-item checklist, Tell #12: Architectural fit',
                        ))

    # 3. Naming convention inconsistency
    naming = pattern_index.get_naming_convention(file_path)
    if naming:
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if naming.language == 'python' and naming.variable_style == 'snake_case':
                # Look for camelCase variable assignments
                for match in re.finditer(
                    r'(?:def|class)\s+([a-z][a-z0-9]*[A-Z][a-zA-Z0-9]*)',
                    line
                ):
                    name = match.group(1)
                    if len(name) > 2:
                        # Skip unittest/pytest conventions
                        unittest_methods = {
                            'setUp', 'tearDown', 'setUpClass', 'tearDownClass',
                            'setUpModule', 'tearDownModule', 'setUpTestData',
                            'addCleanup', 'doCleanups',
                        }
                        if name in unittest_methods:
                            continue
                        # Skip pytest fixtures and test methods
                        if name.startswith('test_') or name.startswith('test'):
                            continue
                        # Skip magic methods (already handled by regex)
                        if name.startswith('__'):
                            continue
                        # Skip common framework methods
                        framework_methods = {
                            'handleSubmit', 'handleSubmitError',
                            'handleClick', 'handleChange', 'handleSubmit',
                            'handleSubmitSuccess', 'handleSubmitFailure',
                            'render', 'renderToString', 'renderToStaticMarkup',
                            'componentDidMount', 'componentDidUpdate',
                            'componentWillUnmount', 'shouldComponentUpdate',
                            'componentWillReceiveProps', 'getDerivedStateFromProps',
                            'getSnapshotBeforeUpdate',
                        }
                        if name in framework_methods:
                            continue
                        # Convert camelCase to snake_case
                        snake_name = ''.join('_' + c.lower() if c.isupper() else c for c in name).lstrip('_')
                        issues.append(UnslopIssue(
                            tell=TellCategory.PATTERN_INCONSISTENCY,
                            severity=Severity.MEDIUM,
                            description=f'"{name}" uses camelCase — file uses snake_case',
                            file_path=file_path,
                            line=i + 1,
                            code_snippet=line.strip()[:60],
                            suggested_fix=f'Rename to snake_case: {snake_name}',
                            confidence=0.75,
                            research_source='Git AutoReview — 12-item checklist, Tell #7: Naming and consistency',
                        ))

    # 4. Helper function inconsistency
    for name in symbols.defined_names:
        helpers = pattern_index.get_helpers_for_purpose(name)
        if helpers:
            issues.append(UnslopIssue(
                tell=TellCategory.PATTERN_INCONSISTENCY,
                severity=Severity.MEDIUM,
                description=f'Function "{name}" duplicates existing helper: "{helpers[0].name}"',
                file_path=file_path,
                suggested_fix=f'Use existing helper "{helpers[0].name}" from {helpers[0].file}',
                confidence=0.7,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #2: Same problem solved five different ways',
            ))

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply pattern inconsistency fixes to source code.

    Args:
        source: Original source code.
        issues: List of pattern inconsistency issues to fix.

    Returns:
        Fixed source code.
    """
    # Pattern inconsistency fixes are mostly suggestions — we can't auto-fix
    # without understanding the full context. Return the source unchanged
    # but flag issues for review.
    return source
