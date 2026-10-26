"""Tiny local web server. Binds to 127.0.0.1 only; serves the page and one JSON endpoint."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / "static"


def make_server(monitor, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/api/status":
                return self._send(200, json.dumps(monitor.snapshot()).encode(), "application/json")
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/app.css": ("app.css", "text/css; charset=utf-8")}
            if path in files:
                name, ctype = files[path]
                return self._send(200, (STATIC / name).read_bytes(), ctype)
            self._send(404, b"not found", "text/plain")

        def log_message(self, *_a):  # quiet
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
