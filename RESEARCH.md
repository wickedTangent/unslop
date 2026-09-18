# UNSLOP — Research: What Separates High-Quality Code from AI-Generated Slop

> A comprehensive synthesis of academic research, industry analysis, and practitioner wisdom on the differences between polished human code and AI-generated code, with the goal of building a tool/extension to refine AI output toward human-quality standards.

---

## Executive Summary

AI does not write *bad* code — it writes **plausible** code. The lines compile, the linter passes, the variable names look reasonable, and on a fast PR review it slides through. That is the exact reason bugs ship. The signature failure of generated code is being a correct answer to a slightly different question.

**The core insight:** Humans are inconsistent in small ways but consistent in approach. AI is the exact opposite — eerily uniform line by line, wildly inconsistent in architecture. You're not looking for bad code. You're looking for code that's *locally perfect and globally incoherent*.

---

## Part 1: The 9 Tells of AI-Generated Code

### Tell 1: Comments That Explain the Obvious, Uniformly
- **AI behavior:** Every function gets a docstring in identical format, including three-line utilities. `# increment the counter` above `counter += 1`. Uniform style across every file.
- **Human behavior:** Humans write comments zero times for obvious code. They drift in style — some functions documented, some not. Comments explain *why*, not *what*.
- **Unslop signal:** Uniform docstrings on trivial functions. `///` doc comments on every method regardless of complexity.

### Tell 2: The Same Problem Solved Five Different Ways
- **AI behavior:** Three HTTP clients. Two date libraries. Four patterns for form validation. Each prompt session picked its own favorite.
- **Human behavior:** Humans adopt the project's existing patterns. Once a pattern is established, they follow it.
- **Unslop signal:** Multiple implementations of the same concept in one codebase. Inconsistent patterns for equivalent operations.

### Tell 3: Dependency Bloat
- **AI behavior:** Packages imported and never called. Libraries pinned in the manifest that nothing uses. Three tools doing one job. AI reaches for a library the way a nervous cook reaches for another pan.
- **Human behavior:** Humans reuse existing dependencies. They feel the cost of adding new ones.
- **Unslop signal:** Imported packages with zero call sites. Dependencies in manifest with no corresponding imports.

### Tell 4: Generic Naming
- **AI behavior:** `data2`, `result_final`, `handleClick2`, `newFunction`, `handleClick3`. Names carry numbering, not intent.
- **Human behavior:** Names carry domain context. A human would call it `formatExportedUserData` or `onSubmitForm`.
- **Unslop signal:** Numeric suffixes on identifiers. Generic terms like `data`, `result`, `temp`, `handle` without context.

### Tell 5: Tests That Don't Test
- **AI behavior:** Tests that assert `true == true` in various costumes. Either no tests at all, or test files that look like coverage in the file tree but prove nothing. Tests assert what the code *does*, not what it *should do*.
- **Human behavior:** Humans write tests for edge cases and failure modes. Tests are written against requirements.
- **Unslop signal:** Exact-value assertions copied from implementation output. No test for the case the ticket was actually about. Missing error-path tests.

### Tell 6: TODO and Placeholder Blocks in Production
- **AI behavior:** `// TODO: add real authentication here` — live, on the internet, taking user data. `// TODO: implement validation`.
- **Human behavior:** Humans are more likely to throw up their hands and leave a function empty with a `NotImplementedError` or raise, rather than ship a TODO with a half-baked implementation.
- **Unslop signal:** TODO blocks in production code. Placeholder implementations that return dummy data.

### Tell 7: Dead Code That Looks Load-Bearing
- **AI behavior:** Whole components, routes, and helpers that nothing calls — fully built, nicely formatted, wired to nothing. The AI built what was asked for, and also what it guessed might be asked for.
- **Human behavior:** Humans delete dead code. They feel the cognitive burden of unused imports and unreachable branches.
- **Unslop signal:** Imported modules with zero call sites. Functions never referenced. Redundant null checks after early returns.

### Tell 8: Error Handling That Swallows Everything
- **AI behavior:** Beautiful try/catch blocks on every function… that catch every exception and do nothing. It looks defensive. It's actually a blindfold.
- **Human behavior:** Humans propagate errors, log them, or handle them specifically. They feel the pain of silent failures.
- **Unslop signal:** `except Exception: pass`. Empty catch blocks. Error handlers that log nothing and return defaults.

### Tell 9: The Patchwork Problem — Locally Valid, Globally Incoherent
- **AI behavior:** A generated endpoint references configuration keys never declared in the project. An import targets a package that does not exist in any registry. A new route omits the authentication guard applied to every sibling endpoint. Each patch is locally valid but globally incoherent.
- **Human behavior:** Humans see the whole codebase. They notice the authentication guard on every sibling endpoint and add one to theirs.
- **Unslop signal:** Cross-file inconsistencies. APIs that don't exist in the project. Missing guards or decorators that exist on all similar code.

---

## Part 2: The 12-Item Code Review Checklist for AI Code

From Git AutoReview's analysis of 470 real pull requests (AI-authored PRs had 10.83 issues/PR vs. 6.45 for human-written — 1.7x more problems):

1. **Requirement alignment** — Does the code actually do what the ticket asked? (AI reads literally and fills gaps with assumptions)
2. **Hallucinated packages** — USENIX Security 2025 measured commercial LMs hallucinating package names at 5.2% rate
3. **Cross-file side effects** — Renames break files outside the diff; AI sees the diff, not the codebase
4. **Hardcoded credentials** — GitGuardian: AI-assisted commits leak secrets at 2x the rate of human commits
5. **Error handling completeness** — AI writes happy path cleanly, skips failure modes (2x human baseline)
6. **Logic correctness** — Every line grammatically correct but overall logic wrong (off-by-one, inverted conditionals)
7. **Naming consistency** — `snake_case`, `camelCase`, `PascalCase` mixed in same module (2x human baseline)
8. **Dead and unreachable code** — Belt-and-suspenders code the type system would never execute
9. **Test coverage for new paths** — Happy path gets a test, error paths don't
10. **Debug artifacts** — `console.log`, `print()`, `debugger`, `TODO` in production
11. **Security vulnerabilities** — Veracode 2025: 45% of AI-generated code introduces at least one OWASP Top 10 vulnerability
12. **Architectural fit** — Respects existing layer boundaries, service layers, repository patterns

---

## Part 3: The Volume-Quality Inverse Law

From the Cai & Tsantalis (2026) study on AI-generated smells:

> **Code volume is a near-perfect predictor of structural degradation.**

As models become more capable, they generate increasingly bloated and coupled code. This is the "Reasoning-Complexity Trade-off": smarter LLMs (e.g., Qwen-480b) inadvertently increase method bloat (Long Method) as they attempt to handle complex logic within single procedural blocks.

Key findings:
- **Functional correctness is decoupled from quality** — running code is just as likely to be structurally flawed as failed code
- **Increasing requirement specificity fails to mitigate degradation** — better prompts don't fix architectural decay
- **The "Modular Mirage"** — agents achieve superficial structural modularity (file separation) but fail to create semantic cohesion

---

## Part 4: The AI-Specific Code Smell Taxonomy

### Code-Level Smells (intra-procedural)
| Smell | AI Manifestation | Human Manifestation |
|-------|-----------------|---------------------|
| **Long Method** | Smarter LLMs pile all logic into single procedural blocks | Under time pressure |
| **God Class** | Too Many Branches — monolithic classes handling everything | Feature creep |
| **Magic Numbers** | Hardcoded values without named constants | Quick-and-dirty |
| **Dead Code** | Belt-and-suspenders checks after returns | Forgotten cleanup |

### Structural Smells (inter-class)
| Smell | AI Manifestation | Human Manifestation |
|-------|-----------------|---------------------|
| **Feature Envy** | Methods accessing another class's data more than their own | Misplaced responsibility |
| **Long Parameter List** | Functions with 5+ parameters to "be thorough" | Over-engineering |
| **Temporal Fields** | Objects with partially initialized state | Incomplete refactoring |

### Architectural Smells (inter-module)
| Smell | AI Manifestation | Human Manifestation |
|-------|-----------------|---------------------|
| **Unstable Dependency** | Tight coupling between unrelated modules | Quick integration |
| **Hub-like Dependency** | One module depending on everything | Central coordinator |
| **Cyclic Dependency** | Circular imports between modules | Accidental coupling |
| **God Module** | One module doing everything | Monolith growth |

---

## Part 5: What High-Quality Human Code Looks Like

### The Consistency Principle
- **Uniform approach, variable execution:** Humans pick a pattern and stick with it across the codebase. The *details* vary (different edge cases, different error messages), but the *approach* is consistent.
- **Comments explain intent, not mechanics:** A human writes `// Use exponential backoff here — API rate limits are aggressive` not `// increment the counter`.
- **Names carry domain context:** `calculateMonthlyRevenue()` not `getData2()`.

### The Cohesion Principle
- **One concern per file/class/method:** Humans feel the cognitive burden of mixed responsibilities and extract them.
- **Dead code gets deleted:** Humans don't ship unused imports or unreachable branches.
- **Error handling is specific:** Humans catch what they can handle, propagate what they can't.

### The Fitting Principle
- **New code looks like old code:** A human reviewer notices the pattern on sibling endpoints and follows it.
- **Service layer respected:** New code goes through existing abstractions.
- **Dependencies are shared:** New code uses existing utilities, not reinvented ones.

---

## Part 7: Research Sources

1. **Justin McKelvey** — "How to Tell If Code Was Written by AI: 9 Tells (2026)" — Pattern reading, vibe debt, real rescue audits
2. **Git AutoReview** — "Code Review Checklist for AI-Generated Code: 12 Things to Verify" — 470 PRs, 10.83 vs 6.45 issues/PR
3. **Thoughtbot** — "How to Review AI Generated PRs" — Workflow adaptation, test quality
4. **Mothukuri & Parizi (2026)** — "The Patchwork Problem in LLM-Generated Code" — Formalizes structural coherence as consistency invariants over graph representations; 8-category failure taxonomy (SRF, PIA, DHI, BCI, RCF, CFC, CCV, SSR) — arXiv:2607.08981
4. **Cai & Tsantalis (2026)** — "AI-Generated Smells: An Analysis of Code and Architecture" — Volume-Quality Inverse Law, Modular Mirage ([arXiv 2605.02741](https://arxiv.org/html/2605.02741))
5. **arXiv 2603.27130** — "Large-Scale Comprehensive Measurement of AI-Generated Code in Real-World Repositories" — 19,816 AI-involved files, 50+ metrics ([arXiv 2603.27130](https://arxiv.org/abs/2603.27130))
6. **Pyor** — "Reviewing AI-Generated Code: A Practical Checklist" — Intent match, hallucinated APIs, edge case auditing
7. **USENIX Security 2025** — 5.2% hallucination rate for package names
8. **GitGuardian (2026)** — AI-assisted commits leak secrets at 2x human rate; 3.2% secret leak rate for Claude Code vs 1.5% baseline ([State of Secrets Sprawl 2026](https://www.gitguardian.com/state-of-secrets-sprawl-report-2026))
9. **Veracode (2025)** — 45% of AI-generated code introduces OWASP Top 10 vulnerability ([2025 GenAI Code Security Report](https://www.veracode.com/wp-content/uploads/2025_GenAI_Code_Security_Report_Final.pdf))
10. **LinearB (2026)** — AI-authored PRs wait 4.6x longer for review, accepted only 32.7% vs 84.4% for human ([2026 Software Engineering Benchmarks](https://linearb.io/resources/software-engineering-benchmarks-report))
11. **McConnell (Code Complete, 2nd Ed.)** — Defect density benchmarks: 15-50 errors/KLOC industry average, 0-25/KLOC for small projects ([Section 27.3](https://flylib.com/books/en/2.823.1.230/1/))
12. **SonarQube** — Code smell thresholds: 0-5/1K ideal, 6-10 needs improvement, 10+ needs action ([Community Discussion](https://community.sonarsource.com/t/what-is-the-acceptable-rate-of-code-smells/131227))
13. **CISQ/ISO 5055** — Standardized defect density per KLOC across security, reliability, performance, maintainability ([CISQ Standards](https://www.it-cisq.org/standards/code-quality-standards/))

---

## Part 8: Slop Score Methodology

### The Problem with Absolute Counts

Early versions of the slop score used absolute thresholds (e.g., "1 security issue = full weight"). This broke on real codebases: a 100K-line project with 1000 security issues scored the same as a 100-line file with one security issue.

### Density-Based Scoring

The current implementation uses **issues per 1000 LOC** (KLOC), following industry standards:

**McConnell (Code Complete)** establishes defect density benchmarks:
- Small projects (< 2K LOC): 0-25 errors/KLOC
- Medium projects (2K-16K LOC): 0-40 errors/KLOC
- Large projects (512K+ LOC): 4-100 errors/KLOC
- Industry average: 15-50 errors/KLOC for delivered code

**SonarQube** provides practical thresholds:
- 0-5 per 1000 lines: ideal (clean)
- 6-10 per 1000 lines: needs improvement
- 10+ per 1000 lines: needs action

**CISQ/ISO 5055** standardizes defect density measurement across quality factors (security, reliability, performance, maintainability).

### Formula

Each tell category has:
- **Weight** (reflects impact severity)
- **Moderate threshold** (below this = 0 score, "clean" range)
- **Critical threshold** (above this = full weight, "action needed" range)

```
score_per_tell = min((density - moderate) / (critical - moderate), 1.0) × weight
total_score = min(sum(score_per_tell), 100.0)
```

**Density thresholds** (issues per 1000 LOC):
| Tell | Moderate | Critical | Weight |
|------|----------|----------|--------|
| Empty error handling | 0.5 | 5.0 | 15 |
| Dead code | 1.0 | 10.0 | 15 |
| Dependency bloat | 1.0 | 10.0 | 15 |
| Generic naming | 5.0 | 50.0 | 15 |
| Pattern inconsistency | 2.0 | 20.0 | 15 |
| Verbose comments | 2.0 | 20.0 | 10 |
| TODO artifacts | 0.5 | 5.0 | 10 |
| Debug artifacts | 0.5 | 5.0 | 5 |
| Test quality | 2.0 | 20.0 | 10 |
| Security vulnerability | 1.0 | 10.0 | 20 |
| Volume anomaly | 1.0 | 10.0 | 5 |
| Cross-file incoherence | 2.0 | 20.0 | 10 |
| Global incoherence | 0.5 | 5.0 | 15 |

### Validation

Tested on 8 real Python repositories (12K-155K lines):

| Repo | Year | Score | Verdict |
|------|------|-------|---------|
| flask | 2010 | 17.3 | Clean |
| requests | 2011 | 26.4 | Mostly clean |
| scrapy | 2010 | 30.5 | Mostly clean |
| fastapi | 2018 | 18.2 | Clean |
| yt-dlp | 2020 | 18.1 | Clean |
| ultralytics | 2022 | 40.0 | Mixed |
| autogen | 2023 | 25.3 | Mostly clean |
| localstack | 2016 | 25.3 | Mostly clean |

Pre-AI era projects (2010-2018) score 17-30. AI-era projects score 25-40. The spread validates the density model.

## Part 8: The Unslop Opportunity — What Can Be Automated

### High-Confidence Automated Fixes (Pattern Matching)

| Tell | Detection | Fix |
|------|-----------|-----|
| Generic naming | Regex for `data\d+`, `result\d+`, `handle\d+`, `newFunction` | Suggest domain-specific names based on context |
| Dead imports | Import analysis with zero call sites | Remove unused imports |
| Dead code | Control flow analysis for unreachable branches | Remove or consolidate |
| Empty catch blocks | AST analysis for `except.*: pass` / `catch.*{} ` | Flag for review, suggest specific handling |
| TODO in production | Regex for `TODO`, `FIXME`, `HACK` in non-test files | Flag, suggest concrete action |
| Debug artifacts | Regex for `console.log`, `print(`, `debugger` | Remove or convert to proper logging |
| Magic numbers | Detect hardcoded numeric literals without named constants | Suggest named constants |
| Verbose comments | Detect comments that restate the code | Remove or enhance with intent |

### Medium-Confidence Automated Fixes (Requires Context)

| Tell | Detection | Fix |
|------|-----------|-----|
| Pattern inconsistency | Cluster similar functions, detect outliers | Suggest aligning with project patterns |
| Dependency bloat | Import vs. usage analysis | Remove unused dependencies |
| Error handling gaps | Trace async paths, detect missing error handling | Suggest try/catch placement |
| Architectural fit | Analyze layer boundaries (controller → service → repo) | Suggest routing through proper layers |
| Test quality | Analyze assertion patterns | Suggest edge case tests |
| Global incoherence | Config key validation, resource path checks | Suggest adding config declarations or correcting paths |

### Low-Confidence (Human-Only)

| Tell | Detection | Fix |
|------|-----------|-----|
| Requirement alignment | Compare code behavior to ticket intent | Requires human judgment |
| Logic correctness | Trace real inputs through functions | Requires domain knowledge |
| Security vulnerabilities | OWASP pattern matching | Requires security expertise |
| Phantom API calls | Symbol resolution against project symbols | Requires type information |

---

## Part 9: Design Principles for the Unslop Tool

1. **Fix the global before the local.** Architecture and consistency matter more than naming. Strip dead code before polishing comments.
2. **Context is king.** Unslop needs to understand the *existing* codebase patterns, not just the new code in isolation.
3. **Suggest, don't rewrite.** The tool should explain *why* something looks AI-generated and offer concrete improvements, not silently rewrite.
4. **The 80/20 rule.** 20% of tells cause 80% of the "this looks AI-generated" feeling. Focus on: generic naming, dead code, pattern inconsistency, and TODO artifacts.
5. **Security first.** Veracode found 45% of AI code has OWASP vulnerabilities. Security fixes should be the highest priority unslop action.
6. **Measure improvement.** Track a "slop score" — a composite metric of the tells above — to show before/after improvement.
