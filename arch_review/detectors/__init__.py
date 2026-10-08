"""Detector registry.

A detector exposes:
  - id: str (e.g. "PY001")
  - run(...) -> List[Finding]

File detectors: run(src: SourceFile, project: Project, config: Config)
Cross-file detectors: run(project: Project, config: Config)
"""
from __future__ import annotations

from typing import List


def file_detectors() -> List:
    from arch_review.detectors.python_ast import PY_DETECTORS
    from arch_review.detectors.generic import GENERIC_DETECTORS

    return list(PY_DETECTORS) + list(GENERIC_DETECTORS)


def crossfile_detectors() -> List:
    from arch_review.detectors.crossfile import XF_DETECTORS

    return list(XF_DETECTORS)


ALL_DETECTOR_IDS: List[str] = None  # type: ignore[assignment]


def all_detector_ids() -> List[str]:
    ids = [d.id for d in file_detectors()]
    ids += [d.id for d in crossfile_detectors()]
    return ids
