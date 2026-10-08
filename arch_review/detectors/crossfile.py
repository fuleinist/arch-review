"""Cross-file, project-wide detectors (XF001-XF003)."""
from __future__ import annotations

import ast
import hashlib
import os
from typing import Dict, List, Optional, Set, Tuple

from arch_review.model import Finding


# ---------------------------------------------------------------------------
# Import graph helpers (Python)
# ---------------------------------------------------------------------------

def _module_name(rel_path: str) -> str:
    """foo/bar/baz.py -> foo.bar.baz ; foo/bar/__init__.py -> foo.bar"""
    p = rel_path.replace("\\", "/")
    if not p.endswith(".py"):
        return ""
    p = p[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def _collect_imports(src) -> Set[str]:
    """Absolute module names imported by a Python file (project-relative guesses)."""
    tree = src.python_ast()
    if tree is None:
        return set()
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # relative import: resolve against the file's package
                pkg = _module_name(src.rel_path).rsplit(".", 1)
                base = src.rel_path.replace("\\", "/").rsplit("/", 1)
                pkg_parts = base[0].split("/")[:-1] if "/" in base[0] else []
                if src.rel_path.replace("\\", "/").endswith("__init__.py"):
                    pkg_parts = base[0].split("/")
                up = node.level - 1
                if up <= len(pkg_parts):
                    root = ".".join(pkg_parts[: len(pkg_parts) - up]) if up else ".".join(pkg_parts)
                    full = (root + "." + node.module) if node.module else root
                    if full:
                        names.add(full)
            elif node.module:
                names.add(node.module)
    return names


def _build_import_graph(project) -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    """Return (module -> imported project modules, module -> rel_path)."""
    mod_to_path: Dict[str, str] = {}
    for src in project.files:
        if src.language == "python":
            mod = _module_name(src.rel_path)
            if mod:
                mod_to_path[mod] = src.rel_path
    graph: Dict[str, Set[str]] = {m: set() for m in mod_to_path}
    for src in project.files:
        if src.language != "python":
            continue
        mod = _module_name(src.rel_path)
        if not mod:
            continue
        for imp in _collect_imports(src):
            # match the import (or its prefix) to a project module
            for target in mod_to_path:
                if target == mod:
                    continue
                if imp == target or imp.startswith(target + "."):
                    graph[mod].add(target)
    return graph, mod_to_path


def _find_cycles(graph: Dict[str, Set[str]]) -> List[List[str]]:
    """All elementary cycles (deduped by rotation), small graphs only."""
    cycles: List[List[str]] = []
    seen: Set[frozenset] = set()

    def dfs(start: str, node: str, path: List[str], on_path: Set[str]):
        for nxt in sorted(graph.get(node, ())):
            if nxt == start and len(path) > 1:
                key = frozenset(path)
                if key not in seen:
                    seen.add(key)
                    cycles.append(list(path))
            elif nxt not in on_path and nxt > start:
                on_path.add(nxt)
                path.append(nxt)
                dfs(start, nxt, path, on_path)
                path.pop()
                on_path.discard(nxt)

    for start in sorted(graph):
        dfs(start, start, [start], {start})
    return cycles


class CircularImportDetector:
    """XF001: circular imports among project modules."""

    id = "XF001"

    def run(self, project, config) -> List[Finding]:
        graph, mod_to_path = _build_import_graph(project)
        findings: List[Finding] = []
        for cycle in _find_cycles(graph)[:20]:
            chain = " -> ".join(cycle + [cycle[0]])
            first_path = mod_to_path.get(cycle[0], "")
            line = 1
            srcfile = project.by_rel(first_path) if first_path else None
            if srcfile is not None:
                for i, l in enumerate(srcfile.lines):
                    if any(f"import {c.split('.')[-1]}" in l or f"from {c}" in l
                           for c in cycle[1:]):
                        line = i + 1
                        break
            findings.append(Finding(
                id=self.id,
                file=first_path or "(project)",
                line=line,
                severity="warning",
                category="architecture",
                message=f"Circular import: {chain}.",
                suggestion=(
                    "Break the cycle: move shared code to a third module, "
                    "or make one side import lazily (inside a function)."
                ),
                extra={"cycle": cycle},
            ))
        return findings


class GodModuleDetector:
    """XF002: module too large or imported by too many project modules."""

    id = "XF002"

    def run(self, project, config) -> List[Finding]:
        max_lines = config.get("max_file_lines")
        fan_in_limit = config.get("fan_in_limit")
        graph, mod_to_path = _build_import_graph(project)
        fan_in: Dict[str, int] = {m: 0 for m in graph}
        for src_mod, targets in graph.items():
            for t in targets:
                if t in fan_in:
                    fan_in[t] += 1
        findings: List[Finding] = []
        reported: Set[str] = set()
        for src in project.files:
            if src.language != "python":
                continue
            n_lines = len(src.lines)
            mod = _module_name(src.rel_path)
            fi = fan_in.get(mod, 0)
            reasons = []
            if n_lines > max_lines:
                reasons.append(f"{n_lines} lines (limit {max_lines})")
            if fi > fan_in_limit:
                reasons.append(f"imported by {fi} modules (limit {fan_in_limit})")
            if reasons and src.rel_path not in reported:
                reported.add(src.rel_path)
                findings.append(Finding(
                    id=self.id,
                    file=src.rel_path,
                    line=1,
                    severity="warning",
                    category="architecture",
                    message=f"God module `{src.rel_path}`: " + ", ".join(reasons) + ".",
                    suggestion=(
                        "Split the module into focused submodules. High fan-in "
                        "means every change risks breaking many importers."
                    ),
                ))
        return findings


# ---------------------------------------------------------------------------
# Duplication (token shingles)
# ---------------------------------------------------------------------------

_TOKEN_RE = None


def _tokenize(text: str) -> List[Tuple[str, int]]:
    """Crude identifier/punct tokenizer; returns (token, line_no) pairs."""
    import re
    global _TOKEN_RE
    if _TOKEN_RE is None:
        _TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\sA-Za-z0-9_]")
    out: List[Tuple[str, int]] = []
    line = 1
    i = 0
    for m in _TOKEN_RE.finditer(text):
        line += text.count("\n", i, m.start())
        i = m.start()
        out.append((m.group(0), line))
    return out


_COMMENT_STRIPPERS = {
    "python": lambda t: t,  # tokenizer already skips comments? no - strip below
}


def _strip_comments(text: str, language: str) -> str:
    import re
    if language == "python":
        text = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', ' "" ', text)
        text = re.sub(r"#[^\n]*", "", text)
    elif language in ("javascript", "typescript", "go", "rust", "java", "c", "cpp", "css"):
        text = re.sub(r"/\*[\s\S]*?\*/", " ", text)
        text = re.sub(r"//[^\n]*", "", text)
    return text


class DuplicationDetector:
    """XF003: duplicated code blocks across files (token shingles)."""

    id = "XF003"

    def run(self, project, config) -> List[Finding]:
        k = config.get("shingle_size")
        min_matches = config.get("min_matching_shingles")
        shingle_map: Dict[str, List[Tuple[str, int]]] = {}
        for src in project.files:
            if src.language in ("json", "yaml", "toml", "markdown", "html", "css"):
                continue
            text = _strip_comments(src.text, src.language)
            tokens = _tokenize(text)
            seen_here: Set[str] = set()
            for i in range(len(tokens) - k + 1):
                window = tokens[i:i + k]
                # skip trivial windows (all punctuation/single identifiers)
                idents = [t for t, _ in window if t.replace("_", "").isalpha() or "_" in t]
                if len(set(idents)) < max(3, k // 2):
                    continue
                key = hashlib.sha1(" ".join(t for t, _ in window).encode()).hexdigest()
                if key in seen_here:
                    continue
                seen_here.add(key)
                shingle_map.setdefault(key, []).append((src.rel_path, window[0][1]))
        # find shingles present in 2+ distinct files
        pair_hits: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
        for key, locs in shingle_map.items():
            files = sorted({f for f, _ in locs})
            if len(files) < 2:
                continue
            for a in range(len(files)):
                for b in range(a + 1, len(files)):
                    la = min(l for f, l in locs if f == files[a])
                    lb = min(l for f, l in locs if f == files[b])
                    pair_hits.setdefault((files[a], files[b]), []).append((la, lb))
        findings: List[Finding] = []
        for (fa, fb), hits in sorted(pair_hits.items()):
            if len(hits) < min_matches:
                continue
            hits.sort()
            start_a = min(h[0] for h in hits)
            start_b = min(h[1] for h in hits)
            findings.append(Finding(
                id=self.id,
                file=fa,
                line=start_a,
                severity="warning",
                category="architecture",
                message=(
                    f"Duplicated code: `{fa}` (from line {start_a}) and `{fb}` "
                    f"(from line {start_b}) share {len(hits)} matching code windows."
                ),
                suggestion=(
                    "Extract the shared logic into one function/module both sides "
                    "import. Copies drift apart silently."
                ),
                extra={"file_a": fa, "file_b": fb, "line_a": start_a, "line_b": start_b,
                       "matching_windows": len(hits)},
            ))
        return findings


XF_DETECTORS = [
    CircularImportDetector(),
    GodModuleDetector(),
    DuplicationDetector(),
]
