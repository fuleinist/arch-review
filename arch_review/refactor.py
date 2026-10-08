"""Refactor suggestion lookup.

Findings already carry before/after examples where computable. This module
maps detector ids to generic guidance so an MCP client can ask for a
suggestion by detector id alone.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

GUIDANCE: Dict[str, Dict[str, Any]] = {
    "PY001": {
        "title": "Extract Function",
        "summary": "Split the long function into smaller named helpers, one responsibility each.",
        "steps": [
            "Identify cohesive blocks (setup / core logic / teardown).",
            "Extract each block into a private helper with a descriptive name.",
            "Keep the original function as a thin orchestrator.",
            "Add tests for each helper as you extract it.",
        ],
    },
    "PY002": {
        "title": "Flatten with guard clauses",
        "summary": "Replace nested ifs with early returns or continue/break guards.",
        "steps": [
            "Invert the outermost condition and return/continue early.",
            "Repeat for each nesting level until depth <= limit.",
            "Extract the deepest block into a helper if it stays complex.",
        ],
    },
    "PY003": {
        "title": "Remove dead import",
        "summary": "Delete the unused import line. Run an import linter in CI to keep it clean.",
        "steps": ["Delete the import.", "Verify no string-based/dynamic usage.", "Re-run tests."],
    },
    "PY004": {
        "title": "Split god class",
        "summary": "Group methods by responsibility into smaller classes; compose them in the original.",
        "steps": [
            "List method groups by the state they touch.",
            "Extract each group into its own class.",
            "Have the original class hold instances and delegate.",
        ],
    },
    "PY005": {
        "title": "Introduce parameter object",
        "summary": "Bundle related parameters into a dataclass or options object.",
        "steps": [
            "Cluster parameters that change together.",
            "Define a dataclass for each cluster.",
            "Update call sites to build the dataclass.",
        ],
    },
    "PY006": {
        "title": "Narrow exception handling",
        "summary": "Catch specific exceptions; never bare except.",
        "steps": [
            "Identify what can actually raise inside the try block.",
            "Catch those exception types explicitly.",
            "Log or re-raise; do not silently pass.",
        ],
    },
    "PY007": {
        "title": "None-default pattern",
        "summary": "Use None as the default and construct the mutable object inside the function.",
        "steps": [
            "Change the default to None.",
            "First line: value = [] if value is None else value.",
            "Update the type hint to Optional[...].",
        ],
    },
    "XF001": {
        "title": "Break the import cycle",
        "summary": "Move shared code to a third module, or import lazily inside a function.",
        "steps": [
            "Draw the cycle: which names does each side need?",
            "Extract the shared names into a new leaf module.",
            "Or move one import inside the function that uses it.",
        ],
    },
    "XF002": {
        "title": "Split god module",
        "summary": "Divide the module into focused submodules grouped by responsibility.",
        "steps": [
            "Group top-level definitions by concern.",
            "Create one submodule per concern.",
            "Re-export from the package __init__ to keep imports stable.",
        ],
    },
    "XF003": {
        "title": "Extract shared logic",
        "summary": "Move the duplicated block into one function both files import.",
        "steps": [
            "Diff the copies to confirm they are still identical.",
            "Extract into a shared helper in a common module.",
            "Replace both copies with calls to the helper.",
        ],
    },
    "GEN001": {
        "title": "Clear marker debt",
        "summary": "Convert TODO/FIXME markers into tracked issues, then remove them.",
        "steps": ["File an issue per marker.", "Reference the issue id or delete the marker."],
    },
    "GEN002": {
        "title": "Wrap long lines",
        "summary": "Wrap lines beyond the limit; configure the formatter to enforce it.",
        "steps": ["Run the project formatter with the line limit.", "Review the diff."],
    },
    "GEN003": {
        "title": "Externalize the secret",
        "summary": "Load secrets from environment or a secret store; rotate anything committed.",
        "steps": [
            "Replace the literal with os.environ lookup.",
            "Add the name to .env.example (value empty).",
            "Rotate the credential if it was ever pushed.",
        ],
    },
}


def suggestion_for(detector_id: str) -> Optional[Dict[str, Any]]:
    return GUIDANCE.get(detector_id)
