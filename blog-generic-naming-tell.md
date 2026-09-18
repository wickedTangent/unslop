# The Generic Naming Tell: What AI Code Looks Like (and Why Our Detector Was Wrong)

## The Tell

Justin McKelvey's fourth tell for AI-generated code is deceptively simple:

> **Generic naming: `data2`, `result_final`, `handleClick2`, `newFunction`. Names carry intent; AI-in-a-hurry code carries numbering.**

It's one of nine tells McKelvey identified from 50+ real codebase rescues. The signal is strong because it's so specific — humans rarely number their identifiers. When they do, it's for a reason: `i1` and `i2` for iteration, `node_1hop` and `node_2hop` for graph traversal. AI-generated code numbers things because it's trying things out and keeping the last one.

## The Problem: Our Detector Was Flagging Everything

When we built the generic naming detector, we used a broad regex:

```python
r'\b([a-zA-Z_][a-zA-Z0-9_]*)(\d+)\b'
```

This matches **any** identifier ending in digits. The result? We scanned 14 TypeScript projects and the `generic_naming` tell produced:

| Repo | generic_naming issues |
|------|----------------------|
| esbuild | 2403 |
| zustand | 854 |
| sqlalchemy | 726 |
| ultralytics | 567 |
| scrapy | 497 |

These are all **real, human-maintained projects**. esbuild (2019) is a bundler. zustand (2019) is a state management library. sqlalchemy (2006) is a database ORM. None of these are AI-generated. Our detector was flagging them as heavily slopped.

## What We Were Getting Wrong

After reading McKelvey's original article and cross-referencing the flagged names, we identified four categories of false positives:

### 1. Year/Version Patterns

Names like `es2020`, `ts39`, `py311`, `node18`, `alpine320` are language version targets, not AI placeholders. Our regex matched `es2020` as `es20` + `20` — a numeric suffix on a 4-character base. But `es2020` means "ES2020 target" in esbuild's configuration. It's not AI slop.

**Fix:** Added explicit year/version pattern exclusions:
```python
_YEAR_VERSION_PATTERNS = [
    r'\bes\d{3,4}\b',      # es2020, es2021, ... es2026
    r'\bts\d{2,3}\b',      # ts39, ts50, ts57
    r'\bpy\d{3,4}\b',      # py311, py312
    r'\bnode\d{2}\b',      # node16, node18, node20
    r'\balpine\d{3}\b',    # alpine320
    r'\bubuntu\d{4}\b',    # ubuntu2204
]
```

### 2. Descriptive Compound Names

McKelvey's examples are `data2` (4-char base) and `handleClick2` (11-char base). But what about `newState1`, `newDevtools2`, `newConnection3`? These are **descriptive compound names** — `new` + `State`, `new` + `Devtools`. They're not generic placeholders.

AI-generated code uses `newFunction`, `newData`, `newResult` — generic category words. Human code uses `newState`, `newDevtools`, `newConnection` — specific compound names. The difference is whether the suffix after `new` describes something.

**Fix:** Added a `_is_descriptive_compound()` check that rejects names where the base is a compound word (detected via camelCase splitting) or starts with a known descriptive prefix (`new`, `handle`, `get`, `set`, `create`, `build`, `format`, `parse`, `validate`, `transform`).

### 3. The "newX" Pattern Was Too Broad

Our original regex `\b(new[A-Z]\w*)\b` matched `newState`, `newDevtools`, `newConnection`, `newOptions` — all legitimate function names. McKelvey's example is `newFunction` — a generic placeholder. The tell isn't "starts with new," it's "starts with new + generic category word."

**Fix:** Restricted to specific generic placeholders:
```python
_GENERIC_NEW_PREFIXES = {
    'Function', 'Data', 'Result', 'Helper', 'Service', 'Controller',
    'Component', 'Util', 'Config', 'Manager', 'Object', 'Handler',
    'Factory', 'Builder', 'Store', 'Validator', 'Parser', 'Serializer',
    'User', 'Process', 'Item', 'Value', 'State', 'Model', 'Class',
    'Type', 'Entity', 'Resource', 'Record', 'Entry', 'Node', 'Key',
    'Field', 'Prop', 'Option', 'Setting', 'Rule', 'Check', 'Filter',
    'Transform', 'Converter', 'Adapter', 'Wrapper', 'Decorator',
}
```

Now `newFunction` is flagged, but `newState` is not.

### 4. We Missed the Underscore Suffix Tell

McKelvey explicitly mentions `result_final`. AI-generated code often appends `_final`, `_backup`, `_copy`, `_temp`, `_old` to indicate tentative naming. We weren't detecting this at all.

**Fix:** Added underscore-suffix pattern detection:
```python
_UNDERSCORE_SUFFIX_PATTERNS = [
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_final\b', ...),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_backup\b', ...),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_copy\b', ...),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_temp\b', ...),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_old\b', ...),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_new\b', ...),
]
```

## The Results

After the fix:

| Repo | Before | After | Reduction |
|------|--------|-------|-----------|
| esbuild | 2403 | 1921 | 20% |
| zustand | 854 | 423 | 50% |
| sqlalchemy | 726 | ~500 | ~30% |
| ultralytics | 567 | ~400 | ~30% |

The biggest wins were year patterns (eliminated entirely) and descriptive compounds (50% reduction in zustand). The remaining inflated counts are a deeper architectural issue: McKelvey's tell is about **clustering** — "four or more together is a diagnosis." Our tool counts individual occurrences, not clusters. A file with 854 instances of `newState1`, `newState2`, `newState3` is likely test code or a library with intentional variant naming, not AI slop.

## The Bigger Picture: Density Matters

McKelvey's full principle is:

> **One tell is a hunch. Four or more together is a diagnosis.**

Our current implementation counts individual occurrences across the entire codebase. A single `data2` in a test file shouldn't count the same as 47 instances of `data2`, `result2`, `handleClick2` in production code.

The fix isn't just better regexes — it's **density-based scoring**. Instead of flagging every occurrence, we should:
1. Count occurrences per file
2. Weight by file type (production vs. test)
3. Cluster by base name (`data2`, `data3`, `data4` = one cluster, not three tells)
4. Only flag when a cluster exceeds a threshold

This is the next phase of the generic naming detector.

## What This Teaches Us About AI Code Detection

The generic naming tell reveals a fundamental challenge in automated AI code detection:

1. **Regexes alone are insufficient.** The same pattern (identifier + digits) can be legitimate (year targets, test variants) or AI-generated (data2, handleClick2). Context matters.

2. **McKelvey's tells are heuristic, not algorithmic.** They're pattern-reading skills developed from 50+ rescues. Translating them to code requires understanding the *intent* behind the tell, not just the surface pattern.

3. **False positives are inevitable without clustering.** Counting individual occurrences inflates scores. A library with 854 test variants isn't slopped — it's well-tested.

4. **The tell is about the pattern, not the instance.** McKelvey's insight is that AI code carries *numbering* as a naming strategy. A single `data2` might be a mistake. Forty-seven `data2` instances across a codebase is a strategy.

## The Bottom Line

Our detector is better now, but it's still noisy. The remaining inflated counts in esbuild and zustand aren't because we missed a regex — they're because McKelvey's tell requires understanding the *context* of the numbering, not just detecting it.

The next step is density-based scoring: cluster by base name, weight by file type, and only flag when the cluster exceeds a threshold. Until then, the generic naming tell is a signal worth watching — but one that needs human judgment to interpret.

---

*This analysis is part of the [unslop](https://github.com/FUTR-Network/unslop) project, which detects and auto-fixes AI-generated code patterns. See [RESEARCH.md](https://github.com/FUTR-Network/unslop/blob/main/RESEARCH.md) for the full research synthesis.*
