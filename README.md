# arch-review

Architecture-aware code review agent. It does not just check diffs. It scans whole
projects, detects anti-patterns across files, and suggests refactors with
before/after examples.

The analysis core is deterministic. No LLM, no API key, no network. An optional
MCP server mode exposes the analysis tools to any MCP-compatible host (Claude,
Cursor, and similar), so your LLM writes the review on top of hard findings.

Zero runtime dependencies. Python 3.9+.

## Install

```bash
pip install -e .        # or: pipx install .
arch-review --version
```

## Usage

### Scan a project

```bash
arch-review scan .                      # text report
arch-review scan src/ --format json     # machine-readable
arch-review scan . --format markdown    # paste into a PR comment
arch-review scan . --fail-on critical   # exit 1 if any critical finding (CI gate)
```

### Review a diff

Report only findings that touch changed lines:

```bash
git diff | arch-review diff
git diff main... | arch-review diff --format markdown
```

### As an MCP server

Add to your MCP client config (Claude Desktop, Cursor, ...):

```json
{
  "mcpServers": {
    "arch-review": {
      "command": "arch-review",
      "args": ["mcp"]
    }
  }
}
```

Tools exposed:

| Tool | Purpose |
|------|---------|
| `scan_project(path)` | findings for a whole project |
| `analyze_file(path)` | findings for one file |
| `review_diff(diff_text)` | findings mapped to a unified diff |
| `get_suggestion(detector_id)` | refactor guidance (title, summary, steps) |

Example: ask your assistant "run scan_project on this repo and write a senior
engineer review of the findings". The findings are deterministic, so two runs
of the same commit produce the same review inputs.

### Self-test

```bash
arch-review selftest
```

## Detectors

Python (AST-based):

| ID | Severity | What it catches |
|----|----------|-----------------|
| PY001 | warning | function longer than `max_function_lines` (60) |
| PY002 | warning | control-flow nesting deeper than `max_nesting_depth` (5) |
| PY003 | suggestion | unused import |
| PY004 | warning | god class (> 20 methods or > 300 lines) |
| PY005 | suggestion | more than `max_params` (7) parameters |
| PY006 | critical | bare `except:` |
| PY007 | critical | mutable default argument |

Cross-file:

| ID | Severity | What it catches |
|----|----------|-----------------|
| XF001 | warning | circular imports between project modules |
| XF002 | warning | god module (> 500 lines or fan-in > 10) |
| XF003 | warning | duplicated code blocks across files (token shingles) |

Any text file:

| ID | Severity | What it catches |
|----|----------|-----------------|
| GEN001 | suggestion | TODO/FIXME marker density above threshold |
| GEN002 | nitpick | lines longer than `max_line_length` (120) |
| GEN003 | critical | probable hardcoded secret (high-entropy literal on a secret-shaped name) |

Every finding can carry a suggestion plus before/after code examples.
`arch-review detectors` lists all ids.

## Configuration

Drop a `.arch-review.json` at the project root (or pass `--config`):

```json
{
  "max_function_lines": 80,
  "max_nesting_depth": 4,
  "max_line_length": 100,
  "exclude": [".git", "node_modules", "generated"],
  "disable_detectors": ["GEN002"]
}
```

All keys are optional. Defaults are in `arch_review/config.py`.

## How duplication detection works

Files are comment-stripped, tokenized, and hashed into 8-token sliding windows
(shingles). A shingle present in two or more files is a duplication candidate.
File pairs with at least 6 matching shingles are reported with line ranges.
This catches copy-paste drift that diff tools miss. Rename an identifier in one
copy and the overlap drops, which is intended: near-copies with divergent names
are exactly what rot into bugs.

## Limitations (v0.1)

- Deep analysis is Python-only. Other languages get the generic detectors.
- Circular-import detection resolves project-relative absolute and simple
  relative imports. Dynamic imports (`importlib`) are invisible.
- The secret detector is heuristic. It flags shapes, not confirmed credentials.
- Duplication detection is token-exact. Formatting differences are ignored,
  renamed identifiers are not.

See `SPEC.md` for the full specification and acceptance criteria.

## Development

```bash
python -m unittest discover -s tests -t .   # 46 tests
```

## License

MIT
