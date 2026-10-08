"""Tests for unified-diff parsing and diff-scoped review (AC3)."""
import unittest

from arch_review.config import Config
from arch_review.diff import parse_diff, review_diff, split_diff_by_file

DIFF_LONG_FUNC = """diff --git a/newmod.py b/newmod.py
--- /dev/null
+++ b/newmod.py
@@ -0,0 +1,72 @@
+def brand_new_giant(alpha):
+    v0 = alpha + 0
+    v1 = v0 + 1
+    v2 = v1 + 1
+    v3 = v2 + 1
+    v4 = v3 + 1
+    v5 = v4 + 1
+    v6 = v5 + 1
+    v7 = v6 + 1
+    v8 = v7 + 1
+    v9 = v8 + 1
+    v10 = v9 + 1
+    v11 = v10 + 1
+    v12 = v11 + 1
+    v13 = v12 + 1
+    v14 = v13 + 1
+    v15 = v14 + 1
+    v16 = v15 + 1
+    v17 = v16 + 1
+    v18 = v17 + 1
+    v19 = v18 + 1
+    v20 = v19 + 1
+    v21 = v20 + 1
+    v22 = v21 + 1
+    v23 = v22 + 1
+    v24 = v23 + 1
+    v25 = v24 + 1
+    v26 = v25 + 1
+    v27 = v26 + 1
+    v28 = v27 + 1
+    v29 = v28 + 1
+    v30 = v29 + 1
+    v31 = v30 + 1
+    v32 = v31 + 1
+    v33 = v32 + 1
+    v34 = v33 + 1
+    v35 = v34 + 1
+    v36 = v35 + 1
+    v37 = v36 + 1
+    v38 = v37 + 1
+    v39 = v38 + 1
+    v40 = v39 + 1
+    v41 = v40 + 1
+    v42 = v41 + 1
+    v43 = v42 + 1
+    v44 = v43 + 1
+    v45 = v44 + 1
+    v46 = v45 + 1
+    v47 = v46 + 1
+    v48 = v47 + 1
+    v49 = v48 + 1
+    v50 = v49 + 1
+    v51 = v50 + 1
+    v52 = v51 + 1
+    v53 = v52 + 1
+    v54 = v53 + 1
+    v55 = v54 + 1
+    v56 = v55 + 1
+    v57 = v56 + 1
+    v58 = v57 + 1
+    v59 = v58 + 1
+    v60 = v59 + 1
+    v61 = v60 + 1
+    v62 = v61 + 1
+    v63 = v62 + 1
+    v64 = v63 + 1
+    v65 = v64 + 1
+    v66 = v65 + 1
+    v67 = v66 + 1
+    v68 = v67 + 1
+    v69 = v68 + 1
+    return v69
"""

DIFF_OTHER_FILE = """diff --git a/other.py b/other.py
--- a/other.py
+++ b/other.py
@@ -1,3 +1,4 @@
 import os
+import sys
 
 def small():
"""


class TestParseDiff(unittest.TestCase):
    def test_parse_new_file(self):
        parsed = parse_diff(DIFF_LONG_FUNC)
        self.assertIn("newmod.py", parsed)
        fd = parsed["newmod.py"]
        self.assertTrue(fd.is_new)
        self.assertIn(1, fd.changed_lines)
        self.assertIn(72, fd.changed_lines)

    def test_parse_context_file(self):
        parsed = parse_diff(DIFF_OTHER_FILE)
        self.assertIn("other.py", parsed)
        self.assertEqual(parsed["other.py"].changed_lines, {2})

    def test_split_by_file(self):
        combined = DIFF_LONG_FUNC + DIFF_OTHER_FILE
        parts = split_diff_by_file(combined)
        self.assertEqual(set(parts), {"newmod.py", "other.py"})


class TestReviewDiff(unittest.TestCase):
    def test_ac3_long_added_function_reported(self):
        findings = review_diff(DIFF_LONG_FUNC, Config())
        py001 = [f for f in findings if f.id == "PY001"]
        self.assertTrue(py001)
        self.assertEqual(py001[0].file, "newmod.py")

    def test_only_changed_files_reported(self):
        combined = DIFF_LONG_FUNC + DIFF_OTHER_FILE
        findings = review_diff(combined, Config())
        files = {f.file for f in findings}
        self.assertIn("newmod.py", files)
        for f in findings:
            self.assertIn(f.file, {"newmod.py", "other.py"})

    def test_untouched_lines_filtered(self):
        # the `import os` line is context, not changed; a finding on an
        # unchanged line of other.py must not appear
        findings = review_diff(DIFF_OTHER_FILE, Config())
        for f in findings:
            if f.file == "other.py" and f.line is not None:
                self.assertIn(f.line, {2})

    def test_empty_diff(self):
        self.assertEqual(review_diff("", Config()), [])


if __name__ == "__main__":
    unittest.main()
