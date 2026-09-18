"""Small source-indexing primitives used by Unslop.

The project originally imported these helpers from ``context-compiler``. That
package changed its public API without preserving the symbol-indexing classes,
which made an otherwise self-contained quality tool fail at startup. Unslop
only needs import bindings, declared names, and a repository file index, so a
stdlib implementation is both more stable and easier to audit.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass(slots=True)
class Symbols:
    """Names needed by the tell detectors."""

    import_bindings: dict[str, str] = field(default_factory=dict)
    defined_names: list[str] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)

    @property
    def imported_modules(self) -> tuple[str, ...]:
        """Unique modules imported by this source file."""
        return tuple(dict.fromkeys(self.import_bindings.values()))


def _python_symbols(source: str) -> Symbols:
    symbols = Symbols()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                symbols.import_bindings[bound_name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound_name = alias.asname or alias.name
                symbols.import_bindings[bound_name] = module
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.defined_names.append(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.function_names.append(node.name)
    return symbols


def _javascript_symbols(source: str) -> Symbols:
    """Best-effort bindings for JS/TS without pulling in a parser package."""
    symbols = Symbols()
    for match in re.finditer(
        r"import\s+(?:\{\s*([^}]+)\s*\}|([\w$]+))\s+from\s+['\"]([^'\"]+)['\"]",
        source,
    ):
        names = match.group(1) or match.group(2) or ""
        for name in names.split(","):
            bound_name = name.strip().split(" as ")[-1].strip()
            if bound_name:
                symbols.import_bindings[bound_name] = match.group(3)
    symbols.defined_names.extend(
        re.findall(r"(?:function|class)\s+([A-Za-z_$][\w$]*)", source)
    )
    symbols.function_names.extend(
        re.findall(r"function\s+([A-Za-z_$][\w$]*)", source)
    )
    return symbols


def extract_symbols(source: str, language: str = "python") -> Symbols:
    """Extract the small symbol set required by Unslop's detectors."""
    if language in {"javascript", "typescript"}:
        return _javascript_symbols(source)
    return _python_symbols(source)


def get_language(suffix: str) -> str | None:
    """Return the detector language for a file suffix."""
    normalized = suffix.casefold()
    if normalized == ".py":
        return "python"
    if normalized in {".ts", ".tsx"}:
        return "typescript"
    if normalized in {".js", ".jsx"}:
        return "javascript"
    return None


@dataclass(slots=True)
class ModuleIndex:
    """Repository files keyed by their relative module-like path."""

    path_to_module: dict[Path, str] = field(default_factory=dict)

    @classmethod
    def build(
        cls, repo_root: Path | str, exclude_dirs: list[str] | None = None
    ) -> "ModuleIndex":
        root = Path(repo_root).resolve()
        excluded = set(exclude_dirs or [])
        files: dict[Path, str] = {}
        supported = {".py", ".ts", ".tsx", ".js", ".jsx"}
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in supported:
                continue
            if any(part in excluded for part in path.relative_to(root).parts):
                continue
            relative = path.relative_to(root).with_suffix("")
            files[path] = ".".join(relative.parts)
        return cls(files)


class SymbolResolver:
    """Compatibility placeholder for older integrations.

    Unslop never used resolver methods directly; retaining the name avoids a
    needless break for callers that imported it from ``pattern_index``.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        return None


__all__ = ["ModuleIndex", "Symbols", "SymbolResolver", "extract_symbols", "get_language"]
