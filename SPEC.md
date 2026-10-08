# arch-review — Specification

## Overview

Architecture-aware code review agent. It does not just check diffs. It scans whole
projects, detects anti-patterns across files, and suggests refactors with before/after
examples. The analysis core is deterministic (no LLM required). An MCP server mode
exposes the analysis tools to any MCP-compatible LLM host (Claude, Cursor, etc.), so
the LLM adds judgment on top of hard findings.

## Why?

Existing PR review tools are surface-level: they comment on diff lines in isolation.
Real review needs cross-file context: circular imports, god modules, duplicated logic,
functions that grew too large. arch-review computes these findings deterministically,
so results are reproducible and free. LLMs consume the findings through MCP and write
the human-facing review.

## Non-goals (v0.1)

- No hosted LLM calls from this tool (the MCP host owns the model).
- No tree-sitter dependency. Python files are parsed with the stdlib `ast` module.
  Other languages get line-based heuristic checks. (Deviation from the original idea:
  keeps zero runtime deps and installable anywhere Python 3.9+ runs.)
- No auto-apply of refactors. Suggestions are examples, not patches.

## Architecture

```
arch-review/
├── pyproject.toml          # packaging, console_scripts entry point
├── SPEC.md
├── README.md
├── arch_review/
│   ├── __init__.py         # version
│   ├── __main__.py         # python -m arch_review
│   ├── cli.py              # argument parsing, scan/diff/mcp/selftest commands
│   ├── config.py           # .arch-review.json config: thresholds, excludes
│   ├── model.py            # Finding dataclass, Severity, Category, JSON serialization
│   ├── scanner.py          # file discovery, language detection, per-file dispatch
│   ├── detectors/
│   │   ├── __init__.py     # detector registry
│   │   ├── python_ast.py   # AST detectors: long function, deep nesting, dead import,
│   │   │                   #   god class, too many params, bare except, mutable default
│   │   ├── crossfile.py    # project-wide: circular imports, god module, duplication
│   │   │                   #   (token shingles), large file
│   │   └── generic.py      # language-agnostic: TODO/FIXME density, long lines,
│   │                       #   trailing whitespace, secrets-shaped strings
│   ├── diff.py             # unified-diff parsing, findings filtered to changed lines
│   ├── refactor.py         # before/after example generator per detector id
│   └── mcp.py              # MCP server (JSON-RPC 2.0 over stdio)
└── tests/
    ├── test_model.py
    ├── test_python_ast.py
    ├── test_crossfile.py
    ├── test_generic.py
    ├── test_diff.py
    ├── test_cli.py         # end-to-end via subprocess
    └── test_mcp.py         # JSON-RPC handshake + tools/call over pipes
```

## Features

- **F1 — `arch-review scan [path]`**: scan a project tree. Emit findings.
  Formats: `--format text|json|markdown` (default text). Exit code 0 always for scan
  (reporting mode), unless `--fail-on <severity>` is given.
- **F2 — `arch-review diff`**: read a unified diff from stdin or `--file`.
  Parse it, map findings onto changed files/lines, report only findings that touch
  changed hunks. Works with `git diff | arch-review diff`.
- **F3 — Python AST detectors** (per file, Python only):
  - `PY001` long function (> `max_function_lines`, default 60)
  - `PY002` deep nesting (> `max_nesting_depth`, default 5)
  - `PY003` unused import
  - `PY004` god class (> `max_class_methods`, default 20, or > `max_class_lines`, default 300)
  - `PY005` too many parameters (> `max_params`, default 7)
  - `PY006` bare `except:`
  - `PY007` mutable default argument
- **F4 — Cross-file detectors** (whole project):
  - `XF001` circular import among project modules
  - `XF002` god module (> `max_file_lines`, default 500, or imported by > `fan_in_limit`, default 10 project modules)
  - `XF003` duplicated code block across files (token shingles, default 8-token window,
    min 6 matching shingles, report file pairs + line ranges)
- **F5 — Generic detectors** (any text file):
  - `GEN001` TODO/FIXME density above threshold
  - `GEN002` line longer than `max_line_length` (default 120)
  - `GEN003` probable hardcoded secret (high-entropy assignment to name matching
    `key|token|secret|password`)
- **F6 — Refactor suggestions**: every finding carries an optional `suggestion`
  (text) and, where computable, `before`/`after` code examples generated from the
  offending source. `--format json` includes them.
- **F7 — Config file** `.arch-review.json` at project root (or `--config <path>`):
  thresholds, `exclude` glob list (defaults: `.git`, `node_modules`, `venv`,
  `__pycache__`, `dist`, `build`), detector enable/disable by id.
- **F8 — MCP server**: `arch-review mcp` speaks MCP (protocol `2024-11-05`) over
  stdio. Tools:
  - `scan_project(path)` → findings JSON
  - `analyze_file(path)` → findings for one file
  - `review_diff(diff_text)` → findings mapped to the diff
  - `get_suggestion(finding_id_context)` → before/after example
- **F9 — `arch-review selftest`**: run the bundled test suite
  (`unittest discover tests/`).
- **F10 — Severity + category schema**:
  severity ∈ `critical|warning|suggestion|nitpick`;
  category ∈ `logic|security|performance|style|testing|docs|architecture`.
  Each finding: `id, file, line, end_line?, severity, category, message, suggestion?,
  before?, after?`.

## Acceptance criteria

- **AC1** `pip install -e .` works. `arch-review --version` prints the version.
- **AC2** `arch-review scan tests/fixtures/sample_bad_project` reports at least one
  finding for each of PY001, PY002, PY003, PY004, PY005, PY006, PY007, XF001, XF003,
  GEN002 using the bundled fixture project.
- **AC3** `git diff | arch-review diff` on a repo with a long added function reports
  PY001 and only findings on changed files.
- **AC4** `--format json` output parses as a JSON array of findings with all schema
  fields; severities and categories are from the fixed vocabularies.
- **AC5** An MCP client handshake (`initialize` → `tools/list` → `tools/call
  scan_project`) succeeds over pipes and returns findings.
- **AC6** Config file thresholds are honored: raising `max_function_lines` above a
  fixture function's length removes its PY001 finding.
- **AC7** Duplicate detector reports the file pair and both line ranges for two files
  sharing a copied block.
- **AC8** Full test suite green via `arch-review selftest` and `python -m unittest`.

## Tech stack

- Python >= 3.9, stdlib only (ast, json, argparse, hashlib, unittest, difflib).
- Zero runtime dependencies. Install with pip.
