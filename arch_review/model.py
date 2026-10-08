"""Finding data model and serialization."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SEVERITIES = ("critical", "warning", "suggestion", "nitpick")
CATEGORIES = ("logic", "security", "performance", "style", "testing", "docs", "architecture")

SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}


@dataclass
class Finding:
    id: str
    file: str
    line: Optional[int]
    severity: str
    category: str
    message: str
    end_line: Optional[int] = None
    suggestion: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"bad severity: {self.severity!r}")
        if self.category not in CATEGORIES:
            raise ValueError(f"bad category: {self.category!r}")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if not d.get("extra"):
            d.pop("extra")
        for key in ("end_line", "suggestion", "before", "after"):
            if d.get(key) is None:
                d.pop(key, None)
        return d

    def to_text(self) -> str:
        loc = self.file
        if self.line is not None:
            loc += f":{self.line}"
            if self.end_line is not None and self.end_line != self.line:
                loc += f"-{self.end_line}"
        head = f"[{self.severity.upper()}] {self.id} {loc}"
        lines = [head, f"  {self.message}"]
        if self.suggestion:
            lines.append(f"  -> {self.suggestion}")
        if self.before is not None and self.after is not None:
            lines.append("  before:")
            lines.extend("    | " + l for l in self.before.splitlines())
            lines.append("  after:")
            lines.extend("    | " + l for l in self.after.splitlines())
        return "\n".join(lines)

    def to_markdown(self) -> str:
        loc = f"`{self.file}`"
        if self.line is not None:
            loc = f"`{self.file}:{self.line}`"
        parts = [f"- **{self.severity.upper()}** `{self.id}` {loc} — {self.message}"]
        if self.suggestion:
            parts.append(f"  - Suggestion: {self.suggestion}")
        if self.before is not None and self.after is not None:
            parts.append("  - Before:\n    ```python\n" + self.before + "\n    ```")
            parts.append("  - After:\n    ```python\n" + self.after + "\n    ```")
        return "\n".join(parts)


def findings_to_json(findings: List[Finding]) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=2)


def sort_findings(findings: List[Finding]) -> List[Finding]:
    return sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER[f.severity], f.file, f.line or 0, f.id),
    )
