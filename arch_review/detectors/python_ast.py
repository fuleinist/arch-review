"""Python AST detectors (PY001-PY007)."""
from __future__ import annotations

import ast
from typing import List, Optional

from arch_review.model import Finding


def _src_segment(src, start: int, end: int, max_lines: int = 12) -> str:
    lines = src.lines[start - 1:end]
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({end - start + 1 - max_lines} more lines)"]
    return "\n".join(lines)


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            best = max(best, _max_nesting(child, depth + 1))
        else:
            best = max(best, _max_nesting(child, depth))
    return best


def _deepest_line(node: ast.AST, depth: int, best: tuple) -> tuple:
    """Return (depth, lineno) of the deepest nesting point."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            cand = _deepest_line(child, depth + 1, best)
            if cand[0] > best[0]:
                best = cand
        else:
            cand = _deepest_line(child, depth, best)
            if cand[0] > best[0]:
                best = cand
    if depth > best[0]:
        best = (depth, getattr(node, "lineno", 0) or best[1])
    return best


class BaseDetector:
    id = "?"

    def run(self, src, project, config) -> List[Finding]:  # pragma: no cover
        raise NotImplementedError


class LongFunctionDetector(BaseDetector):
    """PY001: function body spans more than max_function_lines."""

    id = "PY001"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        limit = config.get("max_function_lines")
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                length = end - node.lineno + 1
                if length > limit:
                    findings.append(Finding(
                        id=self.id,
                        file=src.rel_path,
                        line=node.lineno,
                        end_line=end,
                        severity="warning",
                        category="architecture",
                        message=(
                            f"Function `{node.name}` is {length} lines long "
                            f"(limit {limit}). Long functions are hard to test and reuse."
                        ),
                        suggestion=(
                            f"Extract cohesive blocks of `{node.name}` into smaller "
                            "named helpers, one responsibility each."
                        ),
                        before=_src_segment(src, node.lineno, min(end, node.lineno + 7)),
                        after=(
                            f"def {node.name}(...):\n"
                            f"    part_a = _{node.name}_prepare(...)\n"
                            f"    return _{node.name}_finish(part_a)"
                        ),
                    ))
        return findings


class DeepNestingDetector(BaseDetector):
    """PY002: control-flow nesting deeper than max_nesting_depth."""

    id = "PY002"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        limit = config.get("max_nesting_depth")
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                depth, line = _deepest_line(node, 0, (0, node.lineno))
                if depth > limit:
                    findings.append(Finding(
                        id=self.id,
                        file=src.rel_path,
                        line=line or node.lineno,
                        severity="warning",
                        category="logic",
                        message=(
                            f"Function `{node.name}` nests control flow {depth} deep "
                            f"(limit {limit}). Deep nesting hides edge cases."
                        ),
                        suggestion=(
                            "Use early returns/guard clauses or extract the inner "
                            "block into a helper to flatten the function."
                        ),
                        before=(
                            "def process(items):\n"
                            "    for it in items:\n"
                            "        if it.ok:\n"
                            "            if it.ready:\n"
                            "                handle(it)"
                        ),
                        after=(
                            "def process(items):\n"
                            "    for it in items:\n"
                            "        if not it.ok or not it.ready:\n"
                            "            continue\n"
                            "        handle(it)"
                        ),
                    ))
        return findings


class UnusedImportDetector(BaseDetector):
    """PY003: imported name never referenced."""

    id = "PY003"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        imported = {}  # name -> (lineno, module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    imported[name] = (node.lineno, alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    name = alias.asname or alias.name
                    imported[name] = (node.lineno, node.module or "")
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                base = node
                while isinstance(base, ast.Attribute):
                    base = base.value
                if isinstance(base, ast.Name):
                    used.add(base.id)
        # names referenced in strings (type comments, __all__) count as used
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for name in imported:
                    if name in node.value:
                        used.add(name)
        findings: List[Finding] = []
        for name, (lineno, module) in sorted(imported.items(), key=lambda kv: kv[1][0]):
            if name in used:
                continue
            findings.append(Finding(
                id=self.id,
                file=src.rel_path,
                line=lineno,
                severity="suggestion",
                category="style",
                message=f"Unused import `{name}` (from `{module}`)." if module
                else f"Unused import `{name}`.",
                suggestion=f"Remove the `{name}` import.",
                before=f"import {module}" if module else f"import {name}",
                after="(line removed)",
            ))
        return findings


class GodClassDetector(BaseDetector):
    """PY004: class too large (methods or lines)."""

    id = "PY004"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        max_methods = config.get("max_class_methods")
        max_lines = config.get("max_class_lines")
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [
                n for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            end = getattr(node, "end_lineno", node.lineno)
            length = end - node.lineno + 1
            reasons = []
            if len(methods) > max_methods:
                reasons.append(f"{len(methods)} methods (limit {max_methods})")
            if length > max_lines:
                reasons.append(f"{length} lines (limit {max_lines})")
            if reasons:
                findings.append(Finding(
                    id=self.id,
                    file=src.rel_path,
                    line=node.lineno,
                    end_line=end,
                    severity="warning",
                    category="architecture",
                    message=(
                        f"God class `{node.name}`: " + ", ".join(reasons) +
                        ". Large classes accumulate unrelated responsibilities."
                    ),
                    suggestion=(
                        f"Split `{node.name}` by responsibility: group related "
                        "methods into smaller classes or modules and compose them."
                    ),
                    before=_src_segment(src, node.lineno, min(end, node.lineno + 7)),
                    after=(
                        f"class {node.name}:\n"
                        f"    def __init__(self):\n"
                        f"        self._persistence = {node.name}Store()\n"
                        f"        self._validation = {node.name}Validator()\n"
                        f"    # thin delegation methods only"
                    ),
                ))
        return findings


class TooManyParamsDetector(BaseDetector):
    """PY005: function signature wider than max_params."""

    id = "PY005"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        limit = config.get("max_params")
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args
            names = [a.arg for a in args.args + args.posonlyargs + args.kwonlyargs]
            names = [n for n in names if n not in ("self", "cls")]
            if len(names) > limit:
                sig = ", ".join(names[:10])
                findings.append(Finding(
                    id=self.id,
                    file=src.rel_path,
                    line=node.lineno,
                    severity="suggestion",
                    category="architecture",
                    message=(
                        f"Function `{node.name}` takes {len(names)} parameters "
                        f"(limit {limit}): {sig}. Wide signatures are brittle."
                    ),
                    suggestion=(
                        "Group related parameters into a dataclass or options object."
                    ),
                    before=f"def {node.name}({sig}, ...):",
                    after=(
                        "@dataclass\n"
                        f"class {node.name.title().replace('_', '')}Options:\n"
                        "    ...\n\n"
                        f"def {node.name}(opts: {node.name.title().replace('_', '')}Options):"
                    ),
                ))
        return findings


class BareExceptDetector(BaseDetector):
    """PY006: bare `except:` swallows everything."""

    id = "PY006"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(Finding(
                    id=self.id,
                    file=src.rel_path,
                    line=node.lineno,
                    severity="critical",
                    category="logic",
                    message=(
                        "Bare `except:` catches SystemExit and KeyboardInterrupt "
                        "too, and hides real bugs."
                    ),
                    suggestion="Catch the specific exception, or `except Exception:` at worst.",
                    before="try:\n    do_work()\nexcept:\n    pass",
                    after="try:\n    do_work()\nexcept ValueError as exc:\n    log.warning('bad input: %s', exc)",
                ))
        return findings


class MutableDefaultDetector(BaseDetector):
    """PY007: mutable default argument shared across calls."""

    id = "PY007"

    def run(self, src, project, config) -> List[Finding]:
        tree = src.python_ast()
        if tree is None:
            return []
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            defaults = list(node.args.defaults) + [
                d for d in node.args.kw_defaults if d is not None
            ]
            for d in defaults:
                bad = None
                if isinstance(d, (ast.List, ast.Set, ast.Dict)):
                    bad = type(d).__name__.lower()
                elif isinstance(d, ast.Call):
                    fn = d.func
                    name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                    if name in ("list", "dict", "set"):
                        bad = name
                if bad:
                    findings.append(Finding(
                        id=self.id,
                        file=src.rel_path,
                        line=node.lineno,
                        severity="critical",
                        category="logic",
                        message=(
                            f"Mutable default argument ({bad}) in `{node.name}`. "
                            "The same object is shared by every call."
                        ),
                        suggestion="Default to None and create the object inside the function.",
                        before=f"def {node.name}(items={bad}()):\n    items.append(1)",
                        after=f"def {node.name}(items=None):\n    items = [] if items is None else items\n    items.append(1)",
                    ))
                    break
        return findings


PY_DETECTORS = [
    LongFunctionDetector(),
    DeepNestingDetector(),
    UnusedImportDetector(),
    GodClassDetector(),
    TooManyParamsDetector(),
    BareExceptDetector(),
    MutableDefaultDetector(),
]
