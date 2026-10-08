"""Tests for the MCP server (AC5)."""
import io
import json
import os
import unittest

from arch_review.mcp import PROTOCOL_VERSION, handle_message, serve

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "sample_bad_project")


def rpc(method, params=None, req_id=1):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


class TestHandleMessage(unittest.TestCase):
    def test_initialize(self):
        resp = handle_message(rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        }))
        self.assertEqual(resp["id"], 1)
        result = resp["result"]
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(result["serverInfo"]["name"], "arch-review")

    def test_tools_list(self):
        resp = handle_message(rpc("tools/list", {}, req_id=2))
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(
            sorted(names),
            ["analyze_file", "get_suggestion", "review_diff", "scan_project"],
        )
        for tool in resp["result"]["tools"]:
            self.assertIn("inputSchema", tool)

    def test_notification_returns_none(self):
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.assertIsNone(handle_message(msg))

    def test_unknown_method_error(self):
        resp = handle_message(rpc("bogus/method", {}, req_id=3))
        self.assertEqual(resp["error"]["code"], -32601)

    def test_unknown_tool_is_error_result(self):
        resp = handle_message(rpc("tools/call", {"name": "nope"}, req_id=4))
        self.assertTrue(resp["result"]["isError"])


class TestToolCalls(unittest.TestCase):
    def test_ac5_scan_project_over_stdio(self):
        msgs = [
            rpc("initialize", {"protocolVersion": PROTOCOL_VERSION}, req_id=1),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("tools/list", {}, req_id=2),
            rpc("tools/call", {"name": "scan_project",
                               "arguments": {"path": FIXTURE}}, req_id=3),
        ]
        stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in msgs))
        stdout = io.StringIO()
        code = serve(stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        responses = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(responses), 3)  # notification gets no reply
        scan_resp = responses[2]
        self.assertEqual(scan_resp["id"], 3)
        self.assertFalse(scan_resp["result"]["isError"])
        findings = json.loads(scan_resp["result"]["content"][0]["text"])
        det_ids = {f["id"] for f in findings}
        self.assertIn("PY001", det_ids)
        self.assertIn("XF001", det_ids)

    def test_get_suggestion_tool(self):
        resp = handle_message(rpc("tools/call", {
            "name": "get_suggestion",
            "arguments": {"detector_id": "py001"},
        }, req_id=5))
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(data["detector_id"], "PY001")
        self.assertIn("steps", data)

    def test_review_diff_tool_empty(self):
        resp = handle_message(rpc("tools/call", {
            "name": "review_diff",
            "arguments": {"diff_text": ""},
        }, req_id=6))
        self.assertEqual(json.loads(resp["result"]["content"][0]["text"]), [])

    def test_analyze_file_tool(self):
        target = os.path.join(FIXTURE, "app", "godclass.py")
        resp = handle_message(rpc("tools/call", {
            "name": "analyze_file",
            "arguments": {"path": target},
        }, req_id=7))
        findings = json.loads(resp["result"]["content"][0]["text"])
        self.assertTrue(any(f["id"] == "PY004" for f in findings))


if __name__ == "__main__":
    unittest.main()
