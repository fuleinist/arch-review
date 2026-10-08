"""Tests for the finding model."""
import json
import unittest

from arch_review.model import (
    CATEGORIES,
    SEVERITIES,
    Finding,
    findings_to_json,
    sort_findings,
)


class TestModel(unittest.TestCase):
    def test_valid_finding(self):
        f = Finding(id="PY001", file="a.py", line=1, severity="warning",
                    category="architecture", message="m")
        d = f.to_dict()
        self.assertEqual(d["id"], "PY001")
        self.assertNotIn("extra", d)
        self.assertNotIn("suggestion", d)

    def test_bad_severity_rejected(self):
        with self.assertRaises(ValueError):
            Finding(id="X", file="a", line=1, severity="bogus",
                    category="logic", message="m")

    def test_bad_category_rejected(self):
        with self.assertRaises(ValueError):
            Finding(id="X", file="a", line=1, severity="warning",
                    category="bogus", message="m")

    def test_json_roundtrip(self):
        f = Finding(id="GEN003", file="s.py", line=3, severity="critical",
                    category="security", message="secret", before="b", after="a")
        parsed = json.loads(findings_to_json([f]))
        self.assertEqual(parsed[0]["before"], "b")
        self.assertEqual(parsed[0]["after"], "a")

    def test_sort_order_critical_first(self):
        fs = [
            Finding(id="A", file="z.py", line=1, severity="nitpick", category="style", message="m"),
            Finding(id="B", file="a.py", line=9, severity="critical", category="logic", message="m"),
            Finding(id="C", file="a.py", line=2, severity="warning", category="logic", message="m"),
        ]
        ordered = sort_findings(fs)
        self.assertEqual([f.id for f in ordered], ["B", "C", "A"])

    def test_vocabularies_match_spec(self):
        self.assertEqual(SEVERITIES, ("critical", "warning", "suggestion", "nitpick"))
        self.assertIn("architecture", CATEGORIES)

    def test_text_and_markdown_render(self):
        f = Finding(id="PY001", file="a.py", line=1, end_line=70, severity="warning",
                    category="architecture", message="too long",
                    suggestion="split it", before="x=1", after="y=2")
        self.assertIn("PY001", f.to_text())
        self.assertIn("before:", f.to_text())
        self.assertIn("`a.py:1`", f.to_markdown())


if __name__ == "__main__":
    unittest.main()
