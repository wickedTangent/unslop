"""Tests for cross-file coherence tell detector and fixer."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.report import Severity, TellCategory, UnslopIssue
from unslop.tells.cross_file_coherence import detect, fix


class TestDetect:
    """Tests for the detect function."""

    def test_no_context_returns_empty(self) -> None:
        """Without context, detect returns empty list."""
        source = '''def process():
    return 1
'''
        issues = detect(source, Path("test.py"))
        assert len(issues) == 0

    def test_unknown_module_flagged(self) -> None:
        """Detect imports from unknown modules."""
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            # Add a fake module to the index
            pindex.import_purposes["fake"] = ["fake_module"]
            source = '''from nonexistent_module import something
'''
            issues = detect(source, Path("example.py"), context={'pattern_index': pindex})
            unknown = [i for i in issues if "unknown module" in i.description.lower()]
            assert len(unknown) >= 1

    def test_stdlib_not_flagged(self) -> None:
        """Do not flag standard library imports."""
        source = '''import os
import sys
import json
import re
import pathlib
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("example.py"), context={'pattern_index': pindex})
            unknown = [i for i in issues if "unknown module" in i.description.lower()]
            assert len(unknown) == 0

    def test_common_python_dependency_not_flagged(self) -> None:
        """Known Python packages should not be treated as hallucinated imports."""
        source = '''import numpy
from requests import get
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("src/app.py"), context={'pattern_index': pindex})
            unknown = [i for i in issues if "unknown module" in i.description.lower()]
            assert len(unknown) == 0

    def test_unknown_module_without_manifest_is_low_confidence(self) -> None:
        """An absent dependency manifest reduces certainty, not detection."""
        source = '''from maybe_installed_package import thing
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("src/app.py"), context={'pattern_index': pindex})
            unknown = [i for i in issues if "unknown module" in i.description.lower()]
            assert unknown
            assert unknown[0].confidence == 0.4

    def test_relative_import_not_flagged(self) -> None:
        """Do not flag relative imports."""
        source = '''from .local_module import something
from ..parent_module import something
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("example.py"), context={'pattern_index': pindex})
            unknown = [i for i in issues if "unknown module" in i.description.lower()]
            assert len(unknown) == 0

    def test_endpoint_without_auth(self) -> None:
        """Detect API endpoints without auth guards."""
        source = '''@router.get("/users")
def get_users():
    return users

@router.post("/data")
def post_data():
    return data
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("example.py"), context={'pattern_index': pindex})
            no_auth = [i for i in issues if "auth guard" in i.description.lower()]
            assert len(no_auth) >= 1

    def test_endpoint_with_auth_not_flagged(self) -> None:
        """Do not flag endpoints with auth guards."""
        source = '''@login_required
@router.get("/users")
def get_users():
    return users
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("test.py"), context={'pattern_index': pindex})
            no_auth = [i for i in issues if "auth guard" in i.description.lower()]
            assert len(no_auth) == 0

    def test_no_false_positives_on_normal_code(self) -> None:
        """Do not flag normal code without coherence issues."""
        source = '''import json

def process():
    data = json.loads("{}")
    return data
'''
        from unslop.pattern_index import PatternIndex
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pindex = PatternIndex(Path(tmp))
            issues = detect(source, Path("test.py"), context={'pattern_index': pindex})
            unknown = [i for i in issues if "unknown module" in i.description.lower()]
            assert len(unknown) == 0


class TestFix:
    """Tests for the fix function."""

    def test_fix_returns_source_unchanged(self) -> None:
        """Fix returns source unchanged (suggestions only)."""
        source = '''def process():
    data = load_data()
    return data
'''
        issues = [UnslopIssue(
            tell=TellCategory.CROSS_FILE_INCOHERENCE,
            severity=Severity.MEDIUM,
            description="Import from unknown module",
            file_path=Path("test.py"),
            line=1,
            code_snippet="from nonexistent import something",
            suggested_fix="Check module exists",
            confidence=0.7,
        )]
        result = fix(source, issues)
        assert result == source

    def test_fix_empty_issues_list(self) -> None:
        """Return source unchanged when no issues."""
        source = '''def process():
    data = load_data()
    return data
'''
        result = fix(source, [])
        assert result == source
