"""Configuration: defaults, file loading, merging."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

DEFAULT_EXCLUDES = [
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    "*.egg-info",
]

DEFAULTS: Dict[str, Any] = {
    "max_function_lines": 60,
    "max_nesting_depth": 5,
    "max_class_methods": 20,
    "max_class_lines": 300,
    "max_params": 7,
    "max_file_lines": 500,
    "max_line_length": 120,
    "fan_in_limit": 10,
    "todo_density": 0.02,
    "shingle_size": 8,
    "min_matching_shingles": 6,
    "exclude": list(DEFAULT_EXCLUDES),
    "disable_detectors": [],
}

CONFIG_FILENAME = ".arch-review.json"


class Config:
    def __init__(self, values: Optional[Dict[str, Any]] = None):
        self.values: Dict[str, Any] = dict(DEFAULTS)
        if values:
            self.values.update(values)
        self._disabled = set(self.values.get("disable_detectors") or [])

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def enabled(self, detector_id: str) -> bool:
        return detector_id not in self._disabled

    @property
    def excludes(self) -> List[str]:
        return list(self.values.get("exclude") or [])


def find_config(start: str, explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, CONFIG_FILENAME)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_config(start: str, explicit: Optional[str] = None) -> Config:
    path = find_config(start, explicit)
    if not path:
        return Config()
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: config root must be an object")
    return Config(data)
