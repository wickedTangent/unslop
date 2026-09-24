---
name: unslop
description: >
  Detect and auto-fix AI-generated code patterns ("slop"). Scores code 0-100
  (lower is better) and applies safe auto-fixes with test gating. Use when the
  user asks to unslop code, polish AI-generated code, review for AI tells, or
  get a slop score.
---

# Unslop Skill — Polish AI-Generated Code to Human Quality

> Detect and fix the telltale signs of AI-generated code. Turn plausible code into polished code.

## What It Does

1. **Analyzes** the provided code for AI-generated code patterns (the 13 tells)
2. **Scores** it on a "slop meter" (0-100, **lower is better**)
3. **Auto-fixes** safe issues (Tier 1: verbose comments, TODOs, debug artifacts)
4. **Test-gates** riskier fixes (Tier 2: empty error handling, dead code)
5. **Explains** what was changed and why

## Safety Tiers (unslop fix)

| Tier | Tells | Test-gated? |
|------|-------|-------------|
| 1 | verbose_comments, todo_artifacts, debug_artifacts | No |
| 2 | empty_error_handling, dead_code | Yes |
| 3 | naming, pattern, dependency_bloat, security, test_quality, volume, cross_file, global_incoherence | Never auto-applied |

Tier 3 tells are suggested only — never auto-fixed to avoid breaking domain logic.

## The Slop Score

A composite score from 0-100 based on detected AI tells. **Lower is better.**

| Tell | Weight | Detection |
|------|--------|-----------|
| Generic naming | 15% | `data\d+`, `result\d+`, `handle\d+`, `newFunction` |
| Dead code | 15% | Unused imports, unreachable branches, zero-call-site functions |
| Empty error handling | 15% | `except.*: pass`, empty catch blocks |
| Pattern inconsistency | 15% | Outlier naming/style from codebase cluster |
| Dependency bloat | 15% | Imported packages with zero call sites |
| Verbose comments | 10% | Comments that restate the code, uniform docstrings |
| TODO artifacts | 10% | `TODO`, `FIXME`, `HACK` in production code |
| Debug artifacts | 5% | `console.log`, `print()`, `debugger` |

## The 13 Tells (Research-Backed)

Based on Justin McKelvey's 9 tells, Git AutoReview's 12-item checklist, and Mothukuri & Parizi's (2026) patchwork problem taxonomy:

1. **Comments that explain the obvious, uniformly** — `# increment the counter` above `counter += 1`
2. **The same problem solved five different ways** — Three HTTP clients, two date libraries
3. **Dependency bloat** — Packages imported and never called
4. **Generic naming** — `data2`, `result_final`, `handleClick2`
5. **Tests that don't test** — Assert `true == true` in various costumes
6. **TODO blocks in production** — `// TODO: add real authentication here` live on the internet
7. **Dead code that looks load-bearing** — Fully built, nicely formatted, wired to nothing
8. **Error handling that swallows everything** — `except Exception: pass`
9. **Locally valid, globally incoherent** — References APIs/config that don't exist in the project (Mothukuri & Parizi 2026)
10. **Security vulnerabilities** — OWASP Top 10 patterns (SQLi, XSS, secrets)
11. **Volume anomaly** — Functions/files significantly longer than human-written equivalents
12. **Cross-file incoherence** — Broken cross-file references, missing imports
13. **Debug artifacts** — `console.log`, `print()`, `debugger` in production code

## The Volume-Quality Inverse Law

From Cai & Tsantalis (2026): code volume is a near-perfect predictor of structural degradation. If AI-generated code is significantly longer than what a human would write, flag it.

## Verdicts

| Score | Verdict |
|-------|---------|
| 0-20 | Clean — looks like human-written code |
| 21-40 | Mostly clean — minor AI tells |
| 41-60 | Mixed — several AI tells detected |
| 61-80 | AI-looking — multiple AI tells |
| 81-100 | Slop — strong AI-generated code signals |

## Workflow

```
plan → code → test → fix as needed → test → unslop → retest → fix as needed → retest → PR done
```

Unslop is the quality gate before the PR. It auto-fixes issues.

## Usage

### Scan (read-only analysis)
```bash
unslop scan /path/to/file.py              # Single file
unslop scan /path/to/repo --codebase       # Entire codebase
unslop scan /path/to/file.py --no-json     # Markdown only
```

### Fix (iterative, test-gated improvement)
```bash
unslop fix /path/to/repo                   # Apply safe fixes, run tests
unslop fix /path/to/repo --dry-run         # Preview without applying
unslop fix /path/to/repo --threshold 30    # Target score < 30
unslop fix /path/to/repo --min-confidence 90  # Only high-confidence fixes
unslop fix /path/to/repo --test-cmd "pytest tests/"  # Custom test command
```

### Custom output paths
```bash
unslop scan /path/to/file.py --report custom.md --json-report custom.json
```

### Skip one format
```bash
unslop scan /path/to/file.py --no-markdown    # JSON only
unslop scan /path/to/file.py --no-json        # Markdown only
```

## Output

`unslop` writes **two files by default**:
- `unslopped.md` — human-readable report with issues, severity, and suggested fixes
- `unslopped.json` — structured data for agents (issues array, confidence scores, by_tell breakdown)

Both are always written together unless you use `--no-markdown` or `--no-json`.

### Markdown Report

```markdown
# Unslop Report

**File:** `src/services/user_service.py`
**Slop Score:** 72/100 — AI-looking
**Lines:** 201

## Severity Breakdown

| Severity | Count |
|----------|-------|
| 🔴 critical | 3 |
| 🟠 high | 5 |
| 🟡 medium | 12 |
| 🟢 low | 20 |

## Issues

**Total:** 40 issue(s)

### verbose_comments (20 issues)

- **line 45** — Comment restates code: "# increment the counter"
  ```py
  # increment the counter
  ```
  - **Suggested fix:** Remove comment or replace with why this code exists
  - **Confidence:** 85%
```

### JSON Report (agent-readable)

```json
{
  "version": "1.0",
  "file_path": "src/services/user_service.py",
  "slop_score": 72.0,
  "severity_counts": { "critical": 3, "high": 5, "medium": 12, "low": 20 },
  "issues": [
    {
      "tell": "empty_error_handling",
      "severity": "critical",
      "description": "Empty except block at line 117",
      "line": 117,
      "code_snippet": "except Exception: -> pass",
      "confidence": 0.95
    }
  ],
  "by_tell": {
    "verbose_comments": { "count": 20, "issues": [...] },
    "empty_error_handling": { "count": 1, "issues": [...] }
  }
}
```

## Research Sources

See `RESEARCH.md` for the full research synthesis.

Key sources:
- Justin McKelvey — 9 tells from 50+ real codebase rescues
- Mothukuri & Parizi (2026) — The Patchwork Problem, arXiv:2607.08981
- Cai & Tsantalis (2026) — Volume-Quality Inverse Law, Modular Mirage
- Git AutoReview — 12-item checklist from 470 PRs
- Thoughtbot — How to review AI-generated PRs
- Veracode 2025 — 45% of AI code has OWASP vulnerabilities
- USENIX Security 2025 — 5.2% package name hallucination rate
