"""Language-agnostic detectors (GEN001-GEN003)."""
from __future__ import annotations

import math
import re
from typing import List

from arch_review.model import Finding

TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
SECRET_NAME_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|private[_-]?key|access[_-]?key)\b"
)
SECRET_ASSIGN_RE = re.compile(
    r"""(?ix)
    ^\s*(?:export\s+|const\s+|let\s+|var\s+)?          # optional js/shell prefix
    ["']?([A-Za-z_][A-Za-z0-9_.\-]*)["']?              # name
    \s*[:=]\s*
    ["']([A-Za-z0-9+/_=\-.]{12,})["']                  # quoted value
    """
)
BINARYISH_RE = re.compile(r"[\x00-\x08\x0e-\x1f]")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


class TodoDensityDetector:
    """GEN001: too many TODO/FIXME markers relative to file size."""

    id = "GEN001"

    def run(self, src, project, config) -> List[Finding]:
        if not src.lines:
            return []
        threshold = config.get("todo_density")
        hits = [i + 1 for i, line in enumerate(src.lines) if TODO_RE.search(line)]
        if not hits:
            return []
        density = len(hits) / len(src.lines)
        if density <= threshold or len(hits) < 5:
            return []
        return [Finding(
            id=self.id,
            file=src.rel_path,
            line=hits[0],
            severity="suggestion",
            category="docs",
            message=(
                f"{len(hits)} TODO/FIXME markers in {len(src.lines)} lines "
                f"({density:.1%} density). Marker debt hides unfinished work."
            ),
            suggestion="Convert markers into tracked issues, then fix or delete them.",
        )]


class LongLineDetector:
    """GEN002: lines longer than max_line_length."""

    id = "GEN002"

    def run(self, src, project, config) -> List[Finding]:
        limit = config.get("max_line_length")
        findings: List[Finding] = []
        long_lines = [
            (i + 1, len(line))
            for i, line in enumerate(src.lines)
            if len(line) > limit
        ]
        if not long_lines:
            return []
        first_line, first_len = long_lines[0]
        findings.append(Finding(
            id=self.id,
            file=src.rel_path,
            line=first_line,
            severity="nitpick",
            category="style",
            message=(
                f"{len(long_lines)} line(s) exceed {limit} chars "
                f"(longest: {max(l for _, l in long_lines)} at line {first_line})."
            ),
            suggestion="Wrap long lines for readability and side-by-side diffs.",
        ))
        return findings


class HardcodedSecretDetector:
    """GEN003: high-entropy literal assigned to a secret-shaped name."""

    id = "GEN003"

    def run(self, src, project, config) -> List[Finding]:
        findings: List[Finding] = []
        for i, line in enumerate(src.lines):
            m = SECRET_ASSIGN_RE.match(line)
            if not m:
                continue
            name, value = m.group(1), m.group(2)
            if not SECRET_NAME_RE.search(name):
                continue
            # skip obvious placeholders
            low = value.lower()
            if any(p in low for p in ("xxx", "your", "example", "changeme", "placeholder", "dummy", "test")):
                continue
            if _shannon_entropy(value) < 3.0:
                continue
            findings.append(Finding(
                id=self.id,
                file=src.rel_path,
                line=i + 1,
                severity="critical",
                category="security",
                message=(
                    f"Probable hardcoded secret assigned to `{name}` "
                    "(high-entropy string literal)."
                ),
                suggestion=(
                    "Load the value from an environment variable or secret store. "
                    "If this credential is real, rotate it now."
                ),
                before=f'{name} = "{value[:4]}...{value[-2:]}"',
                after=f'{name} = os.environ["{name.upper()}"]',
            ))
        return findings


GENERIC_DETECTORS = [
    TodoDensityDetector(),
    LongLineDetector(),
    HardcodedSecretDetector(),
]
