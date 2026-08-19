import sys
import unittest
from pathlib import Path

from starlette.requests import Request

PROXY_DIR = Path(__file__).resolve().parents[1] / "proxy"
sys.path.insert(0, str(PROXY_DIR))

import server


def make_request(
    host: str = "echollm.thu.edu.tw",
    method: str = "POST",
    path: str = "/login",
) -> Request:
    headers = [(b"host", host.encode("ascii"))]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": (host, 443),
    }
    return Request(scope)


class SecurityTests(unittest.TestCase):
    def test_login_rate_limit_blocks_after_configured_failures(self):
        client_id = "security-unit-test"
        old_max = server.LOGIN_MAX_FAILURES
        old_block = server.LOGIN_BLOCK_SECONDS
        try:
            server.LOGIN_MAX_FAILURES = 3
            server.LOGIN_BLOCK_SECONDS = 60
            server.clear_login_failures(client_id)
            self.assertEqual(server.record_login_failure(client_id), 0)
            self.assertEqual(server.record_login_failure(client_id), 0)
            self.assertEqual(server.record_login_failure(client_id), 60)
            self.assertGreater(server.login_retry_after(client_id), 0)
        finally:
            server.LOGIN_MAX_FAILURES = old_max
            server.LOGIN_BLOCK_SECONDS = old_block
            server.clear_login_failures(client_id)

    def test_same_origin_host_accepts_only_matching_host(self):
        request = make_request()
        self.assertTrue(server.same_origin_host(request, "https://echollm.thu.edu.tw/login"))
        self.assertFalse(server.same_origin_host(request, "https://example.net/login"))
        self.assertFalse(server.same_origin_host(request, "null"))

    def test_session_tokens_reject_tampering(self):
        token = server.make_token("user", 4_102_444_800)
        self.assertEqual(server.parse_token(token)["sub"], "user")
        self.assertIsNone(server.parse_token(token + "changed"))

    def test_root_renders_login_template_without_session(self):
        response = server.ui(make_request(method="GET", path="/"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CardioLLM |", response.body)
        self.assertIn(b'id="login-form"', response.body)


if __name__ == "__main__":
    unittest.main()
