"""Tests for Unslop's dependency-free source indexing helpers."""

from pathlib import Path

from unslop.symbols import ModuleIndex, extract_symbols


def test_extract_python_symbols_includes_bare_and_from_imports() -> None:
    symbols = extract_symbols(
        "from pathlib import Path as FilePath\nimport json\n\ndef parse():\n    return json.loads('{}')\n"
    )

    assert symbols.import_bindings["FilePath"] == "pathlib"
    assert symbols.import_bindings["json"] == "json"
    assert "parse" in symbols.defined_names
    assert symbols.function_names == ["parse"]
    assert set(symbols.imported_modules) == {"pathlib", "json"}


def test_extract_python_functions_excludes_classes() -> None:
    symbols = extract_symbols("class Service:\n    pass\n\ndef run():\n    pass\n")

    assert symbols.defined_names == ["Service", "run"]
    assert symbols.function_names == ["run"]


def test_extract_javascript_symbols() -> None:
    symbols = extract_symbols("import { readFile as load } from 'fs';\nfunction boot() {}\n", "javascript")

    assert symbols.import_bindings["load"] == "fs"
    assert "boot" in symbols.defined_names
    assert symbols.function_names == ["boot"]


def test_module_index_skips_virtualenv_and_build_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "installed.py").write_text("", encoding="utf-8")

    index = ModuleIndex.build(tmp_path, [".venv"])

    assert tmp_path / "src" / "app.py" in index.path_to_module
    assert tmp_path / ".venv" / "lib" / "installed.py" not in index.path_to_module
