"""End-to-end CLI tests (AC1, AC4)."""
import json
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "sample_bad_project")


def run_cli(*args, input_text=None):
    return subprocess.run(
        [sys.executable, "-m", "arch_review", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        input=input_text,
    )


class TestCli(unittest.TestCase):
    def test_version(self):
        r = run_cli("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("arch-review", r.stdout)

    def test_detectors_lists_ids(self):
        r = run_cli("detectors")
        self.assertEqual(r.returncode, 0)
        ids = r.stdout.split()
        for expected in ("PY001", "XF001", "GEN003"):
            self.assertIn(expected, ids)

    def test_scan_text_format(self):
        r = run_cli("scan", FIXTURE)
        self.assertEqual(r.returncode, 0)
        self.assertIn("PY001", r.stdout)
        self.assertIn("finding(s)", r.stderr)

    def test_ac4_scan_json_schema(self):
        r = run_cli("scan", FIXTURE, "--format", "json")
        self.assertEqual(r.returncode, 0)
        findings = json.loads(r.stdout)
        self.assertIsInstance(findings, list)
        self.assertTrue(findings)
        allowed_sev = {"critical", "warning", "suggestion", "nitpick"}
        allowed_cat = {"logic", "security", "performance", "style",
                       "testing", "docs", "architecture"}
        for f in findings:
            for key in ("id", "file", "severity", "category", "message"):
                self.assertIn(key, f)
            self.assertIn(f["severity"], allowed_sev)
            self.assertIn(f["category"], allowed_cat)

    def test_scan_markdown_format(self):
        r = run_cli("scan", FIXTURE, "--format", "markdown")
        self.assertEqual(r.returncode, 0)
        self.assertIn("**CRITICAL**", r.stdout)

    def test_fail_on_critical_exits_1(self):
        r = run_cli("scan", FIXTURE, "--fail-on", "critical")
        self.assertEqual(r.returncode, 1)

    def test_fail_on_not_triggered_exits_0(self):
        # fixture scan has criticals, so nitpick-only threshold still trips;
        # use an empty temp project instead
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        try:
            r = run_cli("scan", tmp, "--fail-on", "critical")
            self.assertEqual(r.returncode, 0)
            self.assertIn("No findings", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_diff_via_stdin(self):
        diff_text = (
            "diff --git a/x.py b/x.py\n"
            "--- /dev/null\n"
            "+++ b/x.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def f(items=[]):\n"
            "+    return items\n"
        )
        r = run_cli("diff", "--format", "json", input_text=diff_text)
        self.assertEqual(r.returncode, 0)
        findings = json.loads(r.stdout)
        self.assertTrue(any(f["id"] == "PY007" for f in findings))

    @unittest.skipIf(
        os.environ.get("ARCH_REVIEW_IN_SELFTEST"),
        "already inside a selftest run; skip to avoid recursion",
    )
    def test_selftest_command_exists(self):
        # run selftest in a subprocess; the env guard in cli.py stops the
        # nested suite from spawning selftest again
        r = run_cli("selftest")
        self.assertIn(r.returncode, (0, 1))
        self.assertTrue("Ran" in r.stderr or "OK" in r.stderr or "FAILED" in r.stderr)

    def test_no_command_prints_help(self):
        r = run_cli()
        self.assertEqual(r.returncode, 0)
        self.assertIn("usage", r.stdout.lower() + r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
