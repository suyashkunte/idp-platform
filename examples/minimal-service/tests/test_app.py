"""Unit tests for the minimal-service health endpoints (stdlib unittest, plain asserts)."""

from __future__ import annotations

import http.client
import json
import threading
import unittest

from app import HEALTH_PATHS, make_server


class HealthEndpointsTest(unittest.TestCase):
    """Runs the real server on 127.0.0.1 with a free port in a background thread."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = make_server("127.0.0.1", 0)  # bound here, so no sleep is needed before requests
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path: str) -> tuple[int, str, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.getheader("Content-Type", ""), response.read()
        finally:
            conn.close()

    def test_health_paths_return_200_and_status_ok(self) -> None:
        for path in HEALTH_PATHS:
            with self.subTest(path=path):
                status, content_type, body = self._get(path)
                assert status == 200
                assert content_type == "application/json"
                assert json.loads(body) == {"status": "ok"}

    def test_health_paths_are_the_contract_paths(self) -> None:
        assert HEALTH_PATHS == ("/healthz/live", "/healthz/ready", "/healthz/startup")

    def test_unknown_path_returns_404(self) -> None:
        status, _, _ = self._get("/nope")
        assert status == 404


if __name__ == "__main__":
    unittest.main()
