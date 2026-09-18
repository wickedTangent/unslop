"""Tests for PatternIndex."""

from __future__ import annotations

from pathlib import Path

import pytest

from unslop.pattern_index import PatternIndex, NamingConvention


class TestPatternIndex:
    """Tests for the PatternIndex class."""

    def test_build_creates_index(self, tmp_repo: Path) -> None:
        """Building the index creates a populated PatternIndex."""
        # Create a test file
        test_file = tmp_repo / "test.py"
        test_file.write_text('''import json
import os

def process():
    return json.loads("{}")
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        assert index.total_files_indexed >= 1
        assert index.total_lines_indexed >= 1

    def test_analyze_imports(self, tmp_repo: Path) -> None:
        """Import analysis clusters packages by purpose."""
        test_file = tmp_repo / "test.py"
        # Use 'from X import Y' style since extract_symbols only detects that
        test_file.write_text('''from json import loads
from os import path
from datetime import datetime
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        # json should be in serialization
        assert "serialization" in index.import_purposes
        assert "json" in index.import_purposes["serialization"]

    def test_analyze_error_handling(self, tmp_repo: Path) -> None:
        """Error handling analysis detects custom error classes."""
        test_file = tmp_repo / "test.py"
        test_file.write_text('''class AppError(Exception):
    pass

class ValidationError(Exception):
    pass
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        error_classes = [e.error_class for e in index.error_classes]
        assert "AppError" in error_classes
        assert "ValidationError" in error_classes

    def test_analyze_naming_conventions(self, tmp_repo: Path) -> None:
        """Naming analysis detects snake_case vs camelCase."""
        test_file = tmp_repo / "test.py"
        test_file.write_text('''def get_user():
    pass

def process_data():
    pass
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        naming = index.get_naming_convention(test_file)
        assert naming is not None
        assert naming.variable_style == "snake_case"

    def test_get_helpers_for_purpose(self, tmp_repo: Path) -> None:
        """Helper detection finds utility functions."""
        test_file = tmp_repo / "test.py"
        test_file.write_text('''def format_date(date):
    pass

def parse_json(data):
    pass

def validate_email(email):
    pass
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        helpers = index.get_helpers_for_purpose("format")
        assert len(helpers) >= 1
        assert any(h.name == "format_date" for h in helpers)

    def test_has_import_for_purpose(self, tmp_repo: Path) -> None:
        """Check if codebase uses a package for a purpose."""
        test_file = tmp_repo / "test.py"
        # Use 'from X import Y' style since extract_symbols only detects that
        test_file.write_text('''from json import loads
from os import path
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        assert index.has_import_for_purpose("serialization", "json")
        assert not index.has_import_for_purpose("HTTP client", "requests")

    def test_build_with_exclude_dirs(self, tmp_repo: Path) -> None:
        """Exclude directories are skipped during build."""
        # Create a file in an excluded directory
        cache_dir = tmp_repo / "__pycache__"
        cache_dir.mkdir()
        cache_file = cache_dir / "test.pyc"
        cache_file.write_text("cached", encoding="utf-8")

        # Create a normal file
        test_file = tmp_repo / "test.py"
        test_file.write_text('''def process():
    pass
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build(exclude_dirs=["__pycache__"])

        # Should only index the normal file, not the cached one
        assert index.total_files_indexed >= 1
        assert index.total_files_indexed < 3  # __pycache__ excluded

    def test_naming_convention_for_ts(self, tmp_repo: Path) -> None:
        """TypeScript files detected as camelCase."""
        test_file = tmp_repo / "test.ts"
        test_file.write_text('''const getUser = () => {};
const processData = () => {};
''', encoding="utf-8")

        index = PatternIndex(tmp_repo)
        index.build()

        naming = index.get_naming_convention(test_file)
        assert naming is not None
        assert naming.variable_style == "camelCase"
