"""G51: tokencenter copy is loopback-pinned and CSRF-guards POST /api/refresh."""
import os, unittest
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(WS, "modules", "tokencenter", "piggybank.py")

class TestTokencenterLoopbackAndCsrf(unittest.TestCase):
    def setUp(self):
        with open(SRC, encoding="utf-8") as f:
            self.t = f.read()
    def test_bind_pinned_loopback(self):
        self.assertIn('ThreadingHTTPServer(("127.0.0.1", args.port)', self.t)
    def test_post_requires_origin_host_csrf(self):
        self.assertIn("X-CSRF-Nonce", self.t)
        self.assertIn("Origin must exactly match the serving origin", self.t)
        self.assertIn("Host not loopback", self.t)

if __name__ == "__main__":
    unittest.main()
