import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pulse import config as cfg  # noqa: E402
from pulse.checks import check_url  # noqa: E402
from pulse.monitor import Monitor  # noqa: E402


class H(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response({"/ok": 200, "/nf": 404, "/boom": 500}.get(self.path, 200))
        self.end_headers()

    def log_message(self, *a):
        pass


def write(tmp, data):
    p = Path(tmp) / "config.json"
    p.write_text(json.dumps(data))
    return p


class ConfigTests(unittest.TestCase):
    def test_valid_minimal(self):
        with tempfile.TemporaryDirectory() as t:
            c = cfg.load(write(t, {"projects": [{"name": "A", "urls": ["https://example.com"]}]}))
            self.assertEqual(c.projects[0].name, "A")
            self.assertGreaterEqual(c.fast_seconds, 15)

    def test_missing_file_explains(self):
        with self.assertRaises(cfg.ConfigError) as cm:
            cfg.load("/nonexistent/config.json")
        self.assertIn("--demo", str(cm.exception))

    def test_bad_url_property_collection(self):
        with tempfile.TemporaryDirectory() as t:
            for bad in ({"urls": ["ftp://x"]}, {"ga4_property_id": "abc", "service_account": "k.json"},
                        {"errors_collection": "a/b", "service_account": "k.json"}):
                (Path(t) / "k.json").write_text("{}")
                with self.assertRaises(cfg.ConfigError):
                    cfg.load(write(t, {"projects": [{"name": "A", **bad}]}))

    def test_service_account_must_exist_and_be_needed(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(cfg.ConfigError):
                cfg.load(write(t, {"projects": [{"name": "A", "service_account": "keys/none.json"}]}))
            with self.assertRaises(cfg.ConfigError):  # property without a key
                cfg.load(write(t, {"projects": [{"name": "A", "ga4_property_id": "123456"}]}))


class CheckTests(unittest.TestCase):
    def test_url_states(self):
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"
        self.assertTrue(check_url(base + "/ok")["ok"])
        self.assertTrue(check_url(base + "/nf")["ok"])  # alive even if 404
        self.assertFalse(check_url(base + "/boom")["ok"])
        srv.shutdown()
        self.assertFalse(check_url(base + "/ok", timeout=1)["ok"])


class MonitorTests(unittest.TestCase):
    def test_demo_snapshot(self):
        m = Monitor(cfg.demo_config(), demo=True)
        m.poll_fast()
        m.poll_slow()
        snap = m.snapshot()
        status = {p["name"]: p["status"] for p in snap["projects"]}
        self.assertEqual(status["Landing page"], "up")
        self.assertEqual(status["Freezer (Android)"], "slow")
        self.assertEqual(status["License tool (web)"], "down")
        self.assertTrue(snap["demo"])
        self.assertNotIn("service_account", json.dumps(snap))  # keys/paths never reach the browser

    def test_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "h.json"
            c = cfg.Config([cfg.Project("A", ["https://demo.invalid/x"])], 60, 600)
            m = Monitor(c, history_file=f)
            s = m.state["A"]["urls"]["https://demo.invalid/x"]
            s["ms"].extend([100, 120])
            s["ok"].extend([1, 1])
            m._save_history()
            m2 = Monitor(c, history_file=f)
            self.assertEqual(list(m2.state["A"]["urls"]["https://demo.invalid/x"]["ms"]), [100, 120])


if __name__ == "__main__":
    unittest.main()
