"""Integrated scan tests against the fixture project (AC2, AC6, AC7)."""
import json
import os
import shutil
import tempfile
import unittest

from arch_review.config import Config, load_config
from arch_review.scanner import scan_project

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "sample_bad_project")


def scan(cfg=None):
    return scan_project(FIXTURE, cfg or Config())


def ids(findings):
    return {f.id for f in findings}


class TestFixtureScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings = scan()
        cls.ids = ids(cls.findings)

    def test_ac2_all_expected_detectors_fire(self):
        expected = {"PY001", "PY002", "PY003", "PY004", "PY005",
                    "PY006", "PY007", "XF001", "XF003", "GEN002"}
        missing = expected - self.ids
        self.assertEqual(missing, set(), f"detectors did not fire: {missing}")

    def test_py001_targets_long_function(self):
        f = [x for x in self.findings if x.id == "PY001"][0]
        self.assertEqual(f.file, "app/long_and_nested.py")
        self.assertIn("very_long_function", f.message)
        self.assertIsNotNone(f.before)
        self.assertIsNotNone(f.after)

    def test_py003_flags_os_json(self):
        msgs = " ".join(x.message for x in self.findings if x.id == "PY003")
        self.assertIn("os", msgs)
        self.assertIn("json", msgs)

    def test_py006_bare_except_is_critical(self):
        f = [x for x in self.findings if x.id == "PY006"][0]
        self.assertEqual(f.severity, "critical")

    def test_py007_mutable_default_is_critical(self):
        f = [x for x in self.findings if x.id == "PY007"][0]
        self.assertEqual(f.severity, "critical")
        self.assertIn("risky", f.message)

    def test_xf001_reports_cycle_pair(self):
        f = [x for x in self.findings if x.id == "XF001"][0]
        self.assertIn("cycle_a", f.message)
        self.assertIn("cycle_b", f.message)
        self.assertEqual(f.extra.get("cycle") and len(f.extra["cycle"]), 2)

    def test_ac7_xf003_reports_pair_and_lines(self):
        f = [x for x in self.findings if x.id == "XF003"][0]
        pair = {f.extra["file_a"], f.extra["file_b"]}
        self.assertEqual(pair, {"app/dup_one.py", "app/dup_two.py"})
        self.assertGreater(f.extra["line_a"], 0)
        self.assertGreater(f.extra["line_b"], 0)
        self.assertGreaterEqual(f.extra["matching_windows"], 6)

    def test_gen003_flags_api_key_not_password(self):
        msgs = [x.message for x in self.findings if x.id == "GEN003"]
        self.assertTrue(any("api_key" in m for m in msgs))
        self.assertFalse(any("password" in m for m in msgs))  # too short/low entropy

    def test_gen001_todo_density(self):
        self.assertIn("GEN001", self.ids)

    def test_no_findings_outside_fixture_schema(self):
        for f in self.findings:
            self.assertIn(f.severity, ("critical", "warning", "suggestion", "nitpick"))


class TestConfigThresholds(unittest.TestCase):
    def test_ac6_raising_limit_removes_py001(self):
        high = Config({"max_function_lines": 500})
        findings = scan(high)
        py001 = [f for f in findings if f.id == "PY001"
                 and "very_long_function" in f.message]
        self.assertEqual(py001, [])

    def test_disable_detector(self):
        cfg = Config({"disable_detectors": ["GEN003"]})
        findings = scan(cfg)
        self.assertNotIn("GEN003", ids(findings))

    def test_config_file_loading(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, ".arch-review.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"max_function_lines": 999}, fh)
            cfg = load_config(tmp)
            self.assertEqual(cfg.get("max_function_lines"), 999)
            # defaults preserved for other keys
            self.assertEqual(cfg.get("max_params"), 7)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
