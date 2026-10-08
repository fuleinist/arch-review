"""MCP server: JSON-RPC 2.0 over stdio.

Implements protocol 2024-11-05: initialize, tools/list, tools/call.
Zero dependencies: reads newline-delimited JSON-RPC messages from stdin.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from arch_review import __version__
from arch_review.config import load_config
from arch_review.model import findings_to_json, sort_findings

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "scan_project",
        "description": (
            "Scan a project directory for architecture anti-patterns "
            "(long functions, circular imports, god modules, duplication, secrets). "
            "Returns findings as JSON."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project root to scan."},
                "format": {"type": "string", "enum": ["json", "text"], "default": "json"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "analyze_file",
        "description": "Analyze a single source file and return its findings as JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to analyze."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "review_diff",
        "description": (
            "Review a unified diff (e.g. `git diff` output). Returns findings "
            "that touch changed lines, as JSON."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "diff_text": {"type": "string", "description": "Unified diff content."},
            },
            "required": ["diff_text"],
        },
    },
    {
        "name": "get_suggestion",
        "description": (
            "Get refactor guidance for a detector id (e.g. PY001, XF003): "
            "title, summary, and step-by-step instructions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "detector_id": {"type": "string", "description": "Finding id such as PY001."},
            },
            "required": ["detector_id"],
        },
    },
]


def _tool_scan_project(args: Dict[str, Any]) -> str:
    from arch_review.scanner import scan_project

    path = args.get("path") or "."
    config = load_config(path)
    findings = sort_findings(scan_project(path, config))
    if args.get("format") == "text":
        return "\n\n".join(f.to_text() for f in findings) or "No findings."
    return findings_to_json(findings)


def _tool_analyze_file(args: Dict[str, Any]) -> str:
    import os

    from arch_review.scanner import (
        Project, SourceFile, TEXT_EXTENSIONS, read_text, run_file_detectors,
    )

    path = args.get("path") or ""
    if not os.path.isfile(path):
        return json.dumps({"error": f"file not found: {path}"})
    ext = os.path.splitext(path)[1].lower()
    lang = TEXT_EXTENSIONS.get(ext)
    text = read_text(path)
    if text is None:
        return json.dumps({"error": f"cannot read: {path}"})
    config = load_config(os.path.dirname(os.path.abspath(path)) or ".")
    rel = os.path.basename(path)
    src = SourceFile(path, rel, lang or "text", text)
    project = Project(os.path.dirname(os.path.abspath(path)), [src])
    findings = run_file_detectors(project, config)
    findings = [f for f in findings if src.language != "text" or f.id.startswith("GEN")]
    return findings_to_json(sort_findings(findings))


def _tool_review_diff(args: Dict[str, Any]) -> str:
    from arch_review.diff import review_diff

    diff_text = args.get("diff_text") or ""
    if not diff_text.strip():
        return json.dumps([])
    config = load_config(".")
    findings = sort_findings(review_diff(diff_text, config))
    return findings_to_json(findings)


def _tool_get_suggestion(args: Dict[str, Any]) -> str:
    from arch_review.refactor import suggestion_for

    det = (args.get("detector_id") or "").upper()
    data = suggestion_for(det)
    if data is None:
        return json.dumps({"error": f"no guidance for detector id: {det!r}"})
    return json.dumps({"detector_id": det, **data}, indent=2)


TOOL_IMPL = {
    "scan_project": _tool_scan_project,
    "analyze_file": _tool_analyze_file,
    "review_diff": _tool_review_diff,
    "get_suggestion": _tool_get_suggestion,
}


def _result(req_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "arch-review", "version": __version__},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        impl = TOOL_IMPL.get(name or "")
        if impl is None:
            return _result(req_id, {
                "content": [{"type": "text", "text": f"unknown tool: {name!r}"}],
                "isError": True,
            })
        try:
            text = impl(args)
        except Exception as exc:  # report tool errors per MCP spec
            text = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
            return _result(req_id, {
                "content": [{"type": "text", "text": text}],
                "isError": True,
            })
        return _result(req_id, {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        })
    if req_id is not None:
        return _error(req_id, -32601, f"method not found: {method}")
    return None


def serve(stdin=None, stdout=None) -> int:
    """Run the stdio JSON-RPC loop."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = _error(None, -32700, f"parse error: {exc}")
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
            continue
        if isinstance(msg, list):  # batch
            responses = [r for r in (handle_message(m) for m in msg) if r is not None]
            if responses:
                stdout.write(json.dumps(responses) + "\n")
                stdout.flush()
            continue
        resp = handle_message(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
        if msg.get("method") in ("shutdown", "exit"):
            break
    return 0
