# Unslop Architecture Design

## Overview

Unslop is a code analysis and refinement tool that detects AI-generated code patterns and auto-fixes them. It operates at three levels:

1. **File-level** (minimum): Fix the notation, style, and patterns within a single file
2. **Project-level** (ideal): Ensure new code fits the existing codebase patterns
3. **Holistic** (quality exercise): Run a full-codebase quality sweep to raise the overall slop score

## How It Fits in the Workflow

```
plan → code → test → fix as needed → test → unslop → retest → fix as needed → retest → PR done
```

Unslop is the quality gate before the PR. It auto-fixes issues, not just suggests them.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User / Claude Code                        │
│         "unslop this file" / "slop score this"              │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Unslop Library                            │
│  unslop/                                                     │
│  ├── __init__.py              # Public API                   │
│  ├── analyzer.py              # Main orchestrator            │
│  ├── pattern_index.py         # Codebase pattern mapping     │
│  ├── report.py                # Data structures              │
│  ├── cli.py                   # CLI entry point              │
│  └── tells/                   # Individual tell detectors    │
│      ├── naming.py            # Generic naming              │
│      ├── verbose_comments.py  # Obvious comments            │
│      ├── dead_code.py         # Unused imports/functions     │
│      ├── empty_error_handling.py # except: pass             │
│      ├── todo_artifacts.py    # TODO/FIXME blocks           │
│      ├── debug_artifacts.py   # console.log/print           │
│      ├── dependency_bloat.py  # Unused imports              │
│      └── pattern_inconsistency.py # Reinventing the wheel   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Context Compiler (reuse)                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ SymbolResolver — import/call resolution              │   │
│  │ Skeletonizer — AST-based code analysis               │   │
│  │ ModuleIndex — file scanning and indexing             │   │
│  │ extract_symbols — tree-sitter symbol extraction       │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. PatternIndex — Codebase Context Engine

Before analyzing new code, the PatternIndex maps existing codebase patterns:

- **Import clusters** — what packages are used for what purpose
- **Error handling patterns** — what error classes, handlers, middleware exist
- **Naming conventions** — snake_case vs camelCase, PascalCase usage
- **Helper functions** — what common operations already have helpers

This is the "context" that AI code generation misses — the codebase already has solutions for common problems, and the AI introduces new ones instead.

**How it solves the "reinventing the wheel" problem:**
- AI introduces a new HTTP client → PatternIndex flags: "This project uses `httpx` — consider using that instead"
- AI creates a new error class → PatternIndex flags: "This project uses `AppError` — consider using that instead"
- AI imports a new date library → PatternIndex flags: "This project uses `datetime` — consider using that instead"

### 2. Tell Detectors — The 9 Tells

Each tell is a pair of functions:
- `detect(source, file_path, context)` → `list[UnslopIssue]`
- `fix(source, issues)` → `str` (fixed code)

### 3. Analyzer — Orchestrator

The `UnslopAnalyzer` class:
1. Builds the PatternIndex (lazy-loaded)
2. Runs all tell detectors
3. Calculates the slop score
4. Applies fixes
5. Generates the report

### 4. Report — Output Format

Structured report with:
- Slop score (0-100, lower is better)
- Issues grouped by tell category
- Severity ratings
- Suggested fixes
- Verdict

## Tell Detection Matrix

| # | Tell | Weight | Detection Method | Research Source |
|---|------|--------|-----------------|-----------------|
| 1 | Generic naming | 15% | Regex for `data\d+`, `handle\d+`, `newFunction` | Justin McKelvey — Tell #4 |
| 2 | Verbose comments | 10% | Regex for observable restatements, docstring length | Justin McKelvey — Tell #1 |
| 3 | Dead code | 15% | Import call-site analysis, AST reachability | Git AutoReview — Tell #8, McKelvey — Tell #7 |
| 4 | Empty error handling | 15% | AST for `except: pass`, empty catch blocks | McKelvey — Tell #8, Git AutoReview — Tell #5 |
| 5 | TODO artifacts | 10% | Regex for TODO/FIXME/HACK in production | McKelvey — Tell #6, Git AutoReview — Tell #10 |
| 6 | Debug artifacts | 5% | Regex for console.log, print, debugger | Git AutoReview — Tell #10 |
| 7 | Dependency bloat | 15% | Import usage analysis, purpose clustering | McKelvey — Tell #3, Git AutoReview — Tell #2 |
| 8 | Pattern inconsistency | 15% | Cross-reference with PatternIndex | McKelvey — Tell #2, Git AutoReview — Tell #12 |
| 9 | Global incoherence | N/A | Cross-file analysis (future) | McKelvey — Tell #9 |

## Integration Points

### Pi Skill
Unslop operates as a pi skill. The SKILL.md file defines the trigger phrases and behavior.

### Claude Code / Codex
The CLAUDE.md file provides integration instructions for Claude Code and Codex.

### CLI
Command-line interface for standalone use:
```bash
unslop /path/to/file.py
unslop --codebase /path/to/repo
unslop --fix /path/to/file.ts
```

## Slop Score Calculation

```
slop_score = sum(
  weight(tell) * min(issues_found(tell) / threshold(tell), 1.0)
  for tell in all_tells
)
```

Weights:
- Generic naming: 15%
- Dead code: 15%
- Empty error handling: 15%
- Pattern inconsistency: 15%
- Dependency bloat: 15%
- Verbose comments: 10%
- TODO artifacts: 10%
- Debug artifacts: 5%

Thresholds (what triggers max weight for each tell):
- Generic naming: 3+ generic identifiers
- Dead code: 2+ dead items
- Empty error handling: 1+ empty catch
- Pattern inconsistency: 1+ outlier pattern
- Dependency bloat: 2+ unused imports
- Verbose comments: 5+ obvious comments
- TODO artifacts: 1+ TODO in production
- Debug artifacts: 1+ debug statement

## Implementation Status

| Tell | Detector | Fixer | Status |
|------|----------|-------|--------|
| Generic naming | ✅ | ✅ | Done |
| Verbose comments | ✅ | ✅ | Done |
| Dead code | ✅ | ✅ | Done |
| Empty error handling | ✅ | ✅ | Done |
| TODO artifacts | ✅ | ✅ | Done |
| Debug artifacts | ✅ | ✅ | Done |
| Dependency bloat | ✅ | ✅ | Done |
| Pattern inconsistency | ✅ | ⚠️ | Partial (suggests, doesn't auto-fix) |
| Global incoherence | ❌ | ❌ | Future |

## Future Enhancements

1. **Test quality detector** — Detect tests that assert nothing
2. **Security scanner** — SQL injection, hardcoded secrets, missing auth
3. **Volume analysis** — Flag code that's significantly longer than expected
4. **Cross-file coherence** — Detect when new code references APIs/config that don't exist
5. **CI/CD integration** — Block PRs with slop score above threshold
6. **IDE extension** — Real-time slop scoring in VS Code / Cursor
7. **More languages** — Java, C++, C#, Swift (Phase 2+)
