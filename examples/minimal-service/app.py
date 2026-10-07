"""Minimal stdlib HTTP service: the IDP-19 conformance fixture (not a product, not a template).

Answers GET /healthz/live, /healthz/ready and /healthz/startup with 200 and {"status": "ok"}; anything else is 404.
Runs on Python >= 3.9 with the standard library only.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTH_PATHS = ("/healthz/live", "/healthz/ready", "/healthz/startup")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class Handler(BaseHTTPRequestHandler):
    """Serves the three health endpoints; every other path is 404."""

    def do_GET(self) -> None:
        if self.path in HEALTH_PATHS:
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"status": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        """Silence per-request logging."""

    def _send(self, status: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    """Bind a server for `Handler` (port 0 picks a free port)."""
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    server = make_server(host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
