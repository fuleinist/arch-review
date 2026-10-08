"""Command-line interface."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from arch_review import __version__
from arch_review.config import load_config
from arch_review.model import SEVERITY_ORDER, Finding, findings_to_json, sort_findings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arch-review",
        description="Architecture-aware code review agent.",
    )
    p.add_argument("--version", action="version", version=f"arch-review {__version__}")
    sub = p.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="scan a project tree for anti-patterns")
    scan.add_argument("path", nargs="?", default=".", help="project root (default: cwd)")
    scan.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    scan.add_argument("--config", help="explicit config file path")
    scan.add_argument(
        "--fail-on",
        choices=("critical", "warning", "suggestion", "nitpick"),
        help="exit 1 if any finding has this severity or worse",
    )

    diff = sub.add_parser("diff", help="review a unified diff from stdin or --file")
    diff.add_argument("--file", help="read the diff from this file instead of stdin")
    diff.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    diff.add_argument("--config", help="explicit config file path")
    diff.add_argument("--repo", help="repo root for on-disk file fallback (default: cwd)")

    sub.add_parser("mcp", help="run the MCP server (JSON-RPC over stdio)")

    st = sub.add_parser("selftest", help="run the bundled test suite")
    st.add_argument("rest", nargs=argparse.REMAINDER)

    sub.add_parser("detectors", help="list detector ids and exit")

    return p


def _render(findings: List[Finding], fmt: str) -> str:
    findings = sort_findings(findings)
    if fmt == "json":
        return findings_to_json(findings)
    if fmt == "markdown":
        if not findings:
            return "No findings."
        return "\n".join(f.to_markdown() for f in findings)
    if not findings:
        return "No findings."
    return "\n\n".join(f.to_text() for f in findings)


def _fail_on_triggered(findings: List[Finding], level: Optional[str]) -> bool:
    if not level:
        return False
    threshold = SEVERITY_ORDER[level]
    return any(SEVERITY_ORDER[f.severity] <= threshold for f in findings)


def cmd_scan(args) -> int:
    from arch_review.scanner import scan_project

    config = load_config(args.path, args.config)
    findings = scan_project(args.path, config)
    print(_render(findings, args.format))
    print(f"\n{len(findings)} finding(s).", file=sys.stderr)
    if _fail_on_triggered(findings, args.fail_on):
        return 1
    return 0


def cmd_diff(args) -> int:
    from arch_review.diff import review_diff

    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("Empty diff.", file=sys.stderr)
        return 0
    import os
    repo = args.repo or os.getcwd()
    config = load_config(repo, args.config)
    findings = review_diff(text, config, repo_root=repo)
    print(_render(findings, args.format))
    print(f"\n{len(findings)} finding(s) on changed lines.", file=sys.stderr)
    return 0


def cmd_selftest(args) -> int:
    import os
    import unittest

    tests_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")
    if not os.path.isdir(tests_dir):
        print("tests/ directory not found next to the package.", file=sys.stderr)
        return 2
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, top_level_dir=os.path.dirname(tests_dir))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def cmd_detectors(_args) -> int:
    from arch_review.detectors import all_detector_ids

    for did in all_detector_ids():
        print(did)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "diff":
        return cmd_diff(args)
    if args.command == "mcp":
        from arch_review.mcp import serve

        return serve()
    if args.command == "selftest":
        return cmd_selftest(args)
    if args.command == "detectors":
        return cmd_detectors(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
