"""Tests for dependency bloat tell detector and fixer."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.report import Severity, TellCategory, UnslopIssue
from unslop.tells.dependency_bloat import detect, fix


class TestDetect:
    """Tests for the detect function."""

    def test_unused_import(self) -> None:
        """Detect unused imports from 'from X import Y' statements.
        
        Note: The context_compiler.extract_symbols only detects 'from X import Y'
        style imports, not bare 'import X' statements.
        """
        source = '''from os import path
from sys import argv
from json import loads

def process():
    data = loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        # path and argv are unused, loads is used
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) >= 2

    def test_used_import_not_flagged(self) -> None:
        """Do not flag imports that are used."""
        source = '''import json

def process():
    data = json.loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) == 0

    def test_no_context_dependency_bloat(self) -> None:
        """Without context, only detect unused imports from 'from X import Y'."""
        source = '''from os import path
from json import loads

def process():
    data = loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        # path is unused
        assert len(issues) >= 1

    def test_no_false_positives_on_normal_code(self) -> None:
        """Do not flag normal code without dependency bloat."""
        source = '''import json

def process():
    data = json.loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) == 0

    def test_unused_bare_import(self) -> None:
        """Detect unused bare imports."""
        source = '''import os
import sys
import json

def process():
    data = json.loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) >= 2  # os and sys are unused

    def test_used_bare_import_not_flagged(self) -> None:
        """Do not flag used bare imports."""
        source = '''import json

def process():
    data = json.loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) == 0

    def test_import_alias_not_flagged_when_used(self) -> None:
        """Do not flag imported aliases that are used."""
        source = '''import json as j

def process():
    data = j.loads("{}")
    return data
'''
        issues = detect(source, Path("test.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) == 0

    def test_type_checking_import_not_flagged(self) -> None:
        """Type-only imports are intentionally absent at runtime."""
        source = '''from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import User
'''
        issues = detect(source, Path("src/service.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) == 0

    def test_side_effect_import_not_flagged(self) -> None:
        """Known initialization imports can be intentionally unused locally."""
        source = '''import matplotlib.pyplot as plt
'''
        issues = detect(source, Path("src/plot.py"))
        unused = [i for i in issues if "Unused import" in i.description]
        assert len(unused) == 0


class TestFix:
    """Tests for the fix function."""

    def test_fix_removes_unused_imports(self) -> None:
        """Fix removes unused import lines."""
        source = '''import os
import sys
import json

def process():
    data = json.loads("{}")
    return data
'''
        issues = [
            UnslopIssue(
                tell=TellCategory.DEPENDENCY_BLOAT,
                severity=Severity.MEDIUM,
                description='Unused import: "os" from "os"',
                file_path=Path("test.py"),
                line=1,
                code_snippet="import os",
                suggested_fix="Remove import",
                confidence=0.95,
            ),
            UnslopIssue(
                tell=TellCategory.DEPENDENCY_BLOAT,
                severity=Severity.MEDIUM,
                description='Unused import: "sys" from "sys"',
                file_path=Path("test.py"),
                line=2,
                code_snippet="import sys",
                suggested_fix="Remove import",
                confidence=0.95,
            ),
        ]
        result = fix(source, issues)
        assert "import os" not in result
        assert "import sys" not in result
        assert "import json" in result

    def test_fix_empty_issues_list(self) -> None:
        """Return source unchanged when no issues."""
        source = '''def process():
    data = load_data()
    return data
'''
        result = fix(source, [])
        assert result == source

    def test_fix_preserves_used_imports(self) -> None:
        """Ensure fix only removes unused imports, not used ones."""
        source = '''import os
import json

def process():
    data = json.loads("{}")
    return data
'''
        issues = [UnslopIssue(
            tell=TellCategory.DEPENDENCY_BLOAT,
            severity=Severity.MEDIUM,
            description='Unused import: "os" from "os"',
            file_path=Path("test.py"),
            line=1,
            code_snippet="import os",
            suggested_fix="Remove import",
            confidence=0.95,
        )]
        result = fix(source, issues)
        assert "import os" not in result
        assert "import json" in result
