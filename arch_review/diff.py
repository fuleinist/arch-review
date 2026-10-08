"""Unified diff parsing and diff-scoped review."""
from __future__ import annotations

import os
import re
import tempfile
from typing import Dict, List, Optional, Set, Tuple

from arch_review.config import Config
from arch_review.model import Finding

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
DIFF_START_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


class FileDiff:
    """Changed line ranges (new-file numbering) for one file."""

    def __init__(self, path: str):
        self.path = path
        self.changed_lines: Set[int] = set()
        self.is_new = False
        self.is_deleted = False

    def add_hunk(self, start: int, count: Optional[int], added: List[int]):
        self.changed_lines.update(added)


def parse_diff(text: str) -> Dict[str, FileDiff]:
    """Parse a unified diff into per-file changed-line maps."""
    files: Dict[str, FileDiff] = {}
    current: Optional[FileDiff] = None
    new_lineno = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = DIFF_START_RE.match(line)
        if m:
            # peek for --- / +++
            current = None
            i += 1
            continue
        if line.startswith("--- "):
            if line[4:].strip() == "/dev/null":
                pass  # new file
            i += 1
            continue
        m = FILE_RE.match(line)
        if m:
            path = m.group(1).strip()
            if path == "/dev/null":
                current = None
                i += 1
                continue
            current = files.setdefault(path, FileDiff(path))
            if i > 0 and lines[i - 1].startswith("--- /dev/null"):
                current.is_new = True
            new_lineno = 0
            i += 1
            continue
        m = HUNK_RE.match(line)
        if m and current is not None:
            new_lineno = int(m.group(3))
            i += 1
            continue
        if current is not None and new_lineno > 0:
            if line.startswith("+") and not line.startswith("+++"):
                current.changed_lines.add(new_lineno)
                new_lineno += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass  # deleted line: no new-file position
            elif line.startswith(" ") or line == "":
                new_lineno += 1
        i += 1
    return files


def _extract_new_file(diff_text: str, path: str) -> Optional[str]:
    """Reconstruct the post-image of one file from the diff (added/context lines)."""
    files = split_diff_by_file(diff_text)
    chunk = files.get(path)
    if chunk is None:
        return None
    out: List[str] = []
    for line in chunk.splitlines():
        if HUNK_RE.match(line):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
        elif line.startswith(" ") or (line == "" and out):
            out.append(line[1:] if line.startswith(" ") else "")
    return "\n".join(out) + ("\n" if out else "")


def split_diff_by_file(diff_text: str) -> Dict[str, str]:
    """Split a `git diff` blob into {path: per-file diff text}."""
    result: Dict[str, str] = {}
    current_path: Optional[str] = None
    buf: List[str] = []
    for line in diff_text.splitlines():
        m = DIFF_START_RE.match(line)
        if m:
            if current_path is not None:
                result[current_path] = "\n".join(buf)
            current_path = None
            buf = [line]
            continue
        fm = FILE_RE.match(line)
        if fm and current_path is None and buf:
            current_path = fm.group(1).strip()
            buf.append(line)
            continue
        if buf:
            buf.append(line)
    if current_path is not None:
        result[current_path] = "\n".join(buf)
    return result


def review_diff(diff_text: str, config: Config, repo_root: Optional[str] = None) -> List[Finding]:
    """Run detectors against the diff's post-image files.

    Strategy: reconstruct each changed file's new content from the diff, write
    to a temp tree, scan it, then keep only findings whose lines fall inside
    changed hunks.
    """
    from arch_review.scanner import SourceFile, Project, run_file_detectors

    parsed = parse_diff(diff_text)
    if not parsed:
        return []
    findings: List[Finding] = []
    tmpdir = tempfile.mkdtemp(prefix="arch-review-diff-")
    try:
        written: List[SourceFile] = []
        for path, fdiff in parsed.items():
            if not fdiff.changed_lines:
                continue
            content = _extract_new_file(diff_text, path)
            if content is None:
                # fall back to on-disk file when scanning inside a repo
                if repo_root:
                    disk = os.path.join(repo_root, path)
                    if os.path.isfile(disk):
                        with open(disk, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
            if content is None:
                continue
            dest = os.path.join(tmpdir, *path.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            from arch_review.scanner import TEXT_EXTENSIONS
            ext = os.path.splitext(path)[1].lower()
            lang = TEXT_EXTENSIONS.get(ext)
            if lang is None:
                continue
            written.append(SourceFile(dest, path, lang, content))
        if not written:
            return []
        project = Project(tmpdir, written)
        all_findings = run_file_detectors(project, config)
        for f in all_findings:
            fdiff = parsed.get(f.file)
            if fdiff is None:
                continue
            lines = set()
            if f.line is not None:
                lines.add(f.line)
            if f.end_line is not None and f.line is not None:
                lines.update(range(f.line, f.end_line + 1))
            if not lines or lines & fdiff.changed_lines:
                findings.append(f)
        return findings
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
