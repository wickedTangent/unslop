"""PatternIndex — Map existing codebase patterns to detect AI reinvention.

Builds an index of:
- Import clusters (what packages are used for what purpose)
- Error handling patterns (what error classes, handlers, middleware exist)
- Naming conventions (snake_case vs camelCase, PascalCase usage)
- Helper/utility functions (what common operations already have helpers)
- Service/repository patterns (what architectural patterns exist)

This is the "context" that AI code generation misses — the codebase already has
solutions for common problems, and the AI introduces new ones instead.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .symbols import ModuleIndex, extract_symbols, get_language


@dataclass
class ImportCluster:
    """A group of imports that serve a similar purpose."""
    purpose: str  # e.g., "date formatting", "HTTP client", "validation"
    packages: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    call_sites: int = 0


@dataclass
class ErrorHandlingPattern:
    """An existing error handling pattern in the codebase."""
    error_class: str  # e.g., "AppError", "ValidationError"
    base_class: Optional[str] = None
    usage_count: int = 0
    files: list[Path] = field(default_factory=list)
    has_custom_handler: bool = False


@dataclass
class NamingConvention:
    """Naming conventions observed in the codebase."""
    language: str  # "python" or "typescript"
    variable_style: Optional[str] = None  # "snake_case" or "camelCase"
    function_style: Optional[str] = None  # "snake_case" or "camelCase"
    class_style: Optional[str] = None  # "PascalCase" or "CamelCase"
    file_style: Optional[str] = None  # "snake_case" or "camelCase"
    sample_count: int = 0


@dataclass
class HelperFunction:
    """A utility/helper function that solves a common problem."""
    name: str
    purpose: str  # e.g., "format date", "validate email", "parse JSON"
    file: Path
    is_public: bool = True


@dataclass
class PatternIndex:
    """Complete pattern index for a codebase."""
    repo_root: Path

    # Import analysis
    import_purposes: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    import_usage: dict[str, int] = field(default_factory=dict)

    # Error handling
    error_classes: list[ErrorHandlingPattern] = field(default_factory=list)
    try_except_patterns: list[dict] = field(default_factory=list)
    middleware_patterns: list[dict] = field(default_factory=list)

    # Naming
    naming_conventions: dict[str, NamingConvention] = field(default_factory=dict)

    # Helpers
    helper_functions: list[HelperFunction] = field(default_factory=list)

    # General
    total_files_indexed: int = 0
    total_lines_indexed: int = 0

    def build(
        self,
        exclude_dirs: Optional[list[str]] = None,
        max_files: int = 1000,
    ) -> "PatternIndex":
        """Build the pattern index from the codebase.

        Args:
            exclude_dirs: Directories to skip.
            max_files: Maximum files to index (for performance).
        """
        if exclude_dirs is None:
            exclude_dirs = [
                ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
                ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                "build", "dist", "release",
            ]

        index = ModuleIndex.build(self.repo_root, exclude_dirs)

        # Limit files for performance
        files = list(index.path_to_module.keys())[:max_files]

        for file_path in files:
            try:
                source = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            lang = get_language(file_path.suffix) or "python"
            symbols = extract_symbols(source, lang)

            self.total_files_indexed += 1
            self.total_lines_indexed += len(source.splitlines())

            # Analyze imports
            self._analyze_imports(symbols, file_path)

            # Analyze error handling
            self._analyze_error_handling(source, lang, file_path)

            # Analyze naming conventions
            self._analyze_naming(source, lang, file_path)

            self._find_helpers(source, lang, file_path, symbols)

        return self

    def _analyze_imports(self, symbols, file_path: Path) -> None:
        """Cluster imports by purpose."""
        for name, module in symbols.import_bindings.items():
            # Track usage count
            self.import_usage[module] = self.import_usage.get(module, 0) + 1

            # Categorize by purpose (heuristic)
            module_lower = module.lower()
            if any(k in module_lower for k in ["date", "time", "datetime", "luxon", "moment", "chrono"]):
                self.import_purposes["date formatting"].append(module)
            elif any(k in module_lower for k in ["http", "fetch", "axios", "requests", "urllib", "httpx"]):
                self.import_purposes["HTTP client"].append(module)
            elif any(k in module_lower for k in ["valid", "schema", "zod", "pydantic", "validator"]):
                self.import_purposes["validation"].append(module)
            elif any(k in module_lower for k in ["log", "winston", "pino", "structlog"]):
                self.import_purposes["logging"].append(module)
            elif any(k in module_lower for k in ["uuid", "nanoid", "shortid"]):
                self.import_purposes["ID generation"].append(module)
            elif any(k in module_lower for k in ["crypto", "hash", "bcrypt", "argon"]):
                self.import_purposes["cryptographic hashing"].append(module)
            elif any(k in module_lower for k in ["json", "yaml", "toml", "csv", "xml"]):
                self.import_purposes["serialization"].append(module)
            elif any(k in module_lower for k in ["sql", "prisma", "drizzle", "typeorm", "sequelize", "knex"]):
                self.import_purposes["database access"].append(module)
            elif any(k in module_lower for k in ["regex", "regexp", "pattern"]):
                self.import_purposes["pattern matching"].append(module)

    def _analyze_error_handling(
        self, source: str, lang: str, file_path: Path
    ) -> None:
        """Detect existing error handling patterns."""
        if lang == "python":
            # Find class definitions that look like error classes
            for match in re.finditer(
                r"class\s+(\w+Error|\w+Exception)\s*\(\s*(\w+)?\s*\)",
                source
            ):
                error_class = match.group(1)
                base_class = match.group(2)
                pattern = ErrorHandlingPattern(
                    error_class=error_class,
                    base_class=base_class,
                    usage_count=1,
                    files=[file_path],
                )
                self.error_classes.append(pattern)

            for match in re.finditer(
                r"except\s+(\w+(?:\.\w+)*)\s*:",
                source
            ):
                self.try_except_patterns.append({
                    "exception": match.group(1),
                    "file": file_path,
                })

        elif lang in ("typescript", "javascript"):
            for match in re.finditer(
                r"class\s+(\w+Error|\w+Exception)\s+extends\s+(\w+)",
                source
            ):
                error_class = match.group(1)
                base_class = match.group(2)
                pattern = ErrorHandlingPattern(
                    error_class=error_class,
                    base_class=base_class,
                    usage_count=1,
                    files=[file_path],
                )
                self.error_classes.append(pattern)

            for match in re.finditer(
                r"catch\s*\(\s*(\w+)",
                source
            ):
                self.try_except_patterns.append({
                    "exception": match.group(1),
                    "file": file_path,
                })

    def _analyze_naming(self, source: str, lang: str, file_path: Path) -> None:
        """Detect naming conventions in the codebase."""
        if lang == "python":
            # Check variable naming patterns
            snake_vars = len(re.findall(r"def\s+([a-z_]+)\s*\(", source))
            camel_vars = len(re.findall(r"def\s+([a-z][a-zA-Z0-9]+)\s*\(", source))

            naming = NamingConvention(
                language="python",
                variable_style="snake_case" if snake_vars >= camel_vars else "camelCase",
                function_style="snake_case" if snake_vars >= camel_vars else "camelCase",
                sample_count=snake_vars + camel_vars,
            )
            self.naming_conventions[str(file_path)] = naming

        elif lang in ("typescript", "javascript"):
            # Check variable naming patterns
            camel_vars = len(re.findall(r"(?:const|let|var)\s+([a-z][a-zA-Z0-9]+)\s*=", source))
            snake_vars = len(re.findall(r"(?:const|let|var)\s+([a-z]+_[a-z0-9_]+)\s*=", source))

            naming = NamingConvention(
                language=lang,
                variable_style="camelCase" if camel_vars >= snake_vars else "snake_case",
                function_style="camelCase" if camel_vars >= snake_vars else "snake_case",
                sample_count=camel_vars + snake_vars,
            )
            self.naming_conventions[str(file_path)] = naming

    def _find_helpers(
        self, source: str, lang: str, file_path: Path, symbols
    ) -> None:
        """Find utility/helper functions that solve common problems."""
        # Look for functions with names that suggest common operations
        helper_patterns = {
            "format_": "format data",
            "parse_": "parse data",
            "validate_": "validate data",
            "sanitize_": "sanitize data",
            "normalize_": "normalize data",
            "transform_": "transform data",
            "convert_": "convert data",
            "encode_": "encode data",
            "decode_": "decode data",
            "hash_": "hash data",
            "generate_": "generate data",
            "build_": "build data",
            "create_": "create data",
            "is_": "check condition",
            "has_": "check condition",
            "can_": "check capability",
        }

        for name in symbols.defined_names:
            for pattern, purpose in helper_patterns.items():
                if name.startswith(pattern) and len(name) > len(pattern) + 2:
                    self.helper_functions.append(HelperFunction(
                        name=name,
                        purpose=purpose,
                        file=file_path,
                    ))
                    break  # Only match the first pattern

    def get_imports_for_purpose(self, purpose: str) -> list[str]:
        """Get all packages used for a specific purpose."""
        return list(set(self.import_purposes.get(purpose, [])))

    def get_error_classes(self) -> list[ErrorHandlingPattern]:
        """Get all error classes defined in the codebase."""
        return self.error_classes

    def get_naming_convention(self, file_path: Path) -> Optional[NamingConvention]:
        """Get the naming convention for a specific file."""
        return self.naming_conventions.get(str(file_path))

    def get_helpers_for_purpose(self, purpose: str) -> list[HelperFunction]:
        """Get helper functions that match a purpose keyword."""
        return [
            h for h in self.helper_functions
            if purpose.lower() in h.purpose.lower() or h.name.startswith(purpose.lower())
        ]

    def has_import_for_purpose(self, purpose: str, package: str) -> bool:
        """Check if the codebase already uses a package for a purpose."""
        existing = self.get_imports_for_purpose(purpose)
        return package in existing
