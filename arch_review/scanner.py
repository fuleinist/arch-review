"""File discovery and scan orchestration."""
from __future__ import annotations

import fnmatch
import os
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from arch_review.config import Config
from arch_review.model import Finding

TEXT_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".md": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
}

MAX_FILE_BYTES = 2_000_000  # skip files larger than 2 MB


def is_excluded(rel_path: str, excludes: List[str]) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    for pat in excludes:
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
        if fnmatch.fnmatch(rel_path.replace("\\", "/"), pat):
            return True
    return False


def walk_files(root: str, config: Config) -> Iterator[Tuple[str, str, str]]:
    """Yield (abs_path, rel_path, language) for scannable text files."""
    root = os.path.abspath(root)
    excludes = config.excludes
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
        dirnames[:] = [
            d for d in dirnames
            if not is_excluded((rel_dir + "/" + d).lstrip("/"), excludes)
        ]
        for name in sorted(filenames):
            rel = (rel_dir + "/" + name).lstrip("/")
            if is_excluded(rel, excludes):
                continue
            ext = os.path.splitext(name)[1].lower()
            lang = TEXT_EXTENSIONS.get(ext)
            if lang is None:
                continue
            abs_path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(abs_path) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield abs_path, rel, lang


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


class SourceFile:
    """A file loaded for analysis."""

    def __init__(self, abs_path: str, rel_path: str, language: str, text: str):
        self.abs_path = abs_path
        self.rel_path = rel_path
        self.language = language
        self.text = text
        self.lines = text.splitlines()
        self._ast = None
        self._ast_error: Optional[str] = None

    def python_ast(self):
        """Parse and cache the Python AST. Returns None on syntax error."""
        if self._ast is None and self._ast_error is None:
            import ast
            try:
                self._ast = ast.parse(self.text, filename=self.rel_path)
            except SyntaxError as exc:
                self._ast_error = str(exc)
        return self._ast

    @property
    def ast_error(self) -> Optional[str]:
        self.python_ast()
        return self._ast_error


class Project:
    """All source files in the scanned tree."""

    def __init__(self, root: str, files: List[SourceFile]):
        self.root = os.path.abspath(root)
        self.files = files

    def by_rel(self, rel_path: str) -> Optional[SourceFile]:
        for f in self.files:
            if f.rel_path == rel_path.replace("\\", "/"):
                return f
        return None


def load_project(root: str, config: Config) -> Project:
    files: List[SourceFile] = []
    for abs_path, rel, lang in walk_files(root, config):
        text = read_text(abs_path)
        if text is None:
            continue
        files.append(SourceFile(abs_path, rel, lang, text))
    return Project(root, files)


def run_file_detectors(project: Project, config: Config) -> List[Finding]:
    """Run per-file detectors across the project."""
    from arch_review.detectors import file_detectors

    findings: List[Finding] = []
    for src in project.files:
        for detector in file_detectors():
            if not config.enabled(detector.id):
                continue
            findings.extend(detector.run(src, project, config))
    return findings


def run_crossfile_detectors(project: Project, config: Config) -> List[Finding]:
    """Run project-wide detectors."""
    from arch_review.detectors import crossfile_detectors

    findings: List[Finding] = []
    for detector in crossfile_detectors():
        if not config.enabled(detector.id):
            continue
        findings.extend(detector.run(project, config))
    return findings


def scan_project(root: str, config: Config) -> List[Finding]:
    project = load_project(root, config)
    findings = run_file_detectors(project, config)
    findings += run_crossfile_detectors(project, config)
    return findings
