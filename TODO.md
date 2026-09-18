# Unslop — Running TODO

## Completed ✅

### Phase 1: Report Generation ✅ DONE
- [x] `UnslopReport.to_markdown()` — human-readable report
- [x] `UnslopReport.to_json()` — agent-readable structured data
- [x] Both output by default (`unslopped.md` + `unslopped.json`)
- [x] `--no-markdown` / `--no-json` flags to skip individual formats
- [x] `--report` / `--json-report` for custom output paths
- [x] Severity breakdown with emoji indicators
- [x] Issues grouped by tell category with code snippets
- [x] Confidence scores on every issue
- [x] Timestamp in JSON report

### Phase 2: Fix Pipeline ✅ DONE
- [x] `FixPipeline` class — iterative scan→fix→test→re-scan loop
- [x] `unslop fix` subcommand with `--dry-run`, `--run-tests`, `--threshold`
- [x] Safety tiers: Tier 1 (verbose_comments, todo_artifacts, debug_artifacts — no test gate)
- [x] Safety tiers: Tier 2 (empty_error_handling, dead_code, dependency_bloat — test-gated)
- [x] Safety tiers: Tier 3 (naming, pattern, security — never auto-applied)
- [x] Test auto-detection (pytest, npm test, jest, flutter, go, maven, gradle, make)
- [x] Git integration: clean tree check, revert on test failure
- [x] Fix functions re-detect issues after each fix (handles line number shifts)
- [x] `FixResult.to_markdown()` and `to_json()` — iteration history, changes applied/skipped
- [x] `FixResult.write_report()` — writes both formats
- [x] `empty_error_handling` fix: replaces `pass` with `raise` (keeps `except` line for syntax)
- [x] CLI: `--dry-run`, `--run-tests`, `--test-cmd`, `--threshold`, `--min-confidence`, `--max-iterations`
- [x] Exit codes: 0=success, 1=failure, 2=error

### Phase 3: Tell Detector Enhancements ✅ DONE
- [x] `generic_naming` false positive fixes:
  - [x] `_strip_strings_and_comments()` — strip quoted strings and inline comments before regex
  - [x] `_SKIP_ALL_ALPHANUMERIC` — skip common legitimate identifiers (OAuth, JWT, Bearer, SHA, etc.)
  - [x] `_is_likely_token_or_key()` — heuristic for JWT tokens, API keys, base64 strings
  - [x] Context-aware prefix stripping for TypeScript/JS alphanumeric false positives
- [x] Bandit integration — replaced custom Python security regex
- [x] Dynamic dependency resolver — manifest-based resolution (PEP 621, Poetry, uv.lock, requirements.txt)
- [x] Test file false positive filtering
- [x] Density-based scoring overhaul

### Phase 4: GitHub Integration ✅ DONE
- [x] GitHub client (`unslop/github.py`) — `gh` CLI integration
- [x] `unslop fix --create-pr` — create GitHub PR with fixes
- [x] PR body generation with summary, changes table, next steps
- [x] Branch/commit/push workflow automation
- [x] End-to-end integration tests (17 tests)

### Tell Detectors (13/13) ✅ DONE

| # | Tell | Status | Research Source |
|---|------|--------|-----------------|
| 1 | Empty error handling | ✅ DONE | McKelvey Tell #8, Git AutoReview #5 |
| 2 | Dead code | ✅ DONE | Git AutoReview #8, McKelvey Tell #7 |
| 3 | Dependency bloat | ✅ DONE | McKelvey Tell #3, Git AutoReview #2 |
| 4 | Generic naming | ✅ DONE | McKelvey Tell #4 |
| 5 | Pattern inconsistency | ✅ (suggests) | McKelvey Tell #2, Git AutoReview #12 |
| 6 | Verbose comments | ✅ DONE | McKelvey Tell #1 |
| 7 | TODO artifacts | ✅ DONE | McKelvey Tell #6, Git AutoReview #10 |
| 8 | Debug artifacts | ✅ DONE | Git AutoReview #10 |
| 9 | Test quality | ✅ DONE | Cai & Tsantalis 2026, Veracode 2025 |
| 10 | Security scanner | ✅ DONE | Veracode 2025, OWASP Top 10 |
| 11 | Volume analysis | ✅ DONE | McConnell "Code Complete", Git AutoReview |
| 12 | Cross-file coherence | ✅ DONE | McKelvey Tell #2, Cai & Tsantalis 2026 |
| 13 | Global incoherence | ✅ DONE | McKelvey Tell #9, Mothukuri & Parizi 2026 |

### Infrastructure
- [x] Core library (`unslop/`)
- [x] PatternIndex (codebase context)
- [x] Pi skill
- [x] Claude Code integration
- [x] CLI entry point
- [x] Package (`pyproject.toml`)
- [x] Before/after examples
- [x] Research synthesis
- [x] Architecture design
- [x] Dependency resolver

### Validation Dataset
- [x] 15 Python repos baseline (scrapy, requests, fastapi, yt-dlp, rich, pydantic, httpx, celery, sqlalchemy, etc.)
- [x] 14 TypeScript repos baseline (express, react, vue/core, tailwindcss, astro, axios, esbuild, mobx, nextjs, playwright, remix, tanstack-query, vite, zustand)
- [x] Self-scanning (unslop: 39.3/100 overall, ~10/100 production-only)
- [x] TypeScript baseline: 14 repos scanned (see table below)

## Testing

- **266 tests** across 18 test files
- All 13 tell detectors: detect + fix tested
- Core modules: PatternIndex, Report, FixPipeline, TestRunner, GitOps, CLI, GitHub, DependencyResolver
- Integration tests isolated via `test_z_` prefix

## In Progress

### Phase 5: Verbose Comments Fixer Enhancement
- [x] Research: identify useful vs. restating comment patterns
- [x] Implement context-aware verbose comment detection
- [x] Improved `_extract_useful_context()` — uses `" to "`/`" for "` markers
- [x] Expanded `IMPERATIVE_VERBS` for better detection
- [ ] Add test cases for nuanced comment scenarios
- [ ] Benchmark against real codebase comment patterns

### Phase 6: TypeScript Baseline Expansion
- [x] Cloned 10 additional TypeScript repos (15 total)
- [x] Scanned all 15 with consistent 50-file sample
- [x] Compiled TypeScript baseline results
- [x] Updated STATUS.md with TS baseline data
- [x] Cleaned up repos (deleted TypeScript 668 MB repo)

## Out of Scope (Explicitly Excluded)

- [ ] IDE extension — real-time slop scoring in VS Code / Cursor
- [ ] More languages — Java, C++, Swift (Phase 2+)
- [ ] CI/CD integration — GitHub Actions workflow, CI/CD pipeline gating

## Medium Priority (Future)

- [ ] `pattern_inconsistency` auto-fix — requires full codebase context
- [ ] Cross-file coherence improvements — more framework detection
- [ ] Better verbose_comments fixer — distinguish useful vs. restating comments (Phase 5)

## Notes

- Slop score: 0-100, **lower is better**
- Verdicts: Clean (0-20), Mostly clean (21-40), Mixed (41-60), AI-looking (61-80), Slop (81-100)
- Workflow: plan → code → test → fix → unslop → retest → PR
- Global incoherence (Tell #9) formalized by Mothukuri & Parizi (2026) — "The Patchwork Problem" arXiv:2607.08981
