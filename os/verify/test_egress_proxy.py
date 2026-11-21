"""O4: the domain-allowlist egress proxy, tested with loopback sockets and injected resolver/connector."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_egress_proxy as ep
from aiws_egress_proxy import EgressProxy, Policy, PolicyError, is_ip_literal

PUBLIC = "93.184.216.34"

class Echo:
    def __init__(self):
        self.server = socket.socket(); self.server.bind(("127.0.0.1", 0)); self.server.listen(8)
        self.port = self.server.getsockname()[1]
        self.connections = 0
        threading.Thread(target=self.run, daemon=True).start()
    def run(self):
        while True:
            try:
                c, _ = self.server.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self.echo, args=(c,), daemon=True).start()
    @staticmethod
    def echo(c):
        try:
            while True:
                d = c.recv(4096)
                if not d:
                    return
                c.sendall(d)
        except OSError:
            pass
        finally:
            c.close()
    def close(self):
        self.server.close()

class Base(unittest.TestCase):
    ENTRIES = ["api.example.com", "*.cdn.example.net", "# comment"]
    def setUp(self):
        self.echo = Echo()
        self.resolutions = {"api.example.com": [PUBLIC], "x.cdn.example.net": [PUBLIC]}
        self.connected = []
        def resolver(host):
            if host not in self.resolutions:
                raise socket.gaierror("no such host")
            return self.resolutions[host]
        def connector(address, port, timeout):
            self.connected.append((address, port))
            return socket.create_connection(("127.0.0.1", self.echo.port), timeout=2)
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "egress.jsonl"
        self.proxy = EgressProxy(Policy(self.ENTRIES), port=0, resolver=resolver, connector=connector, log_path=self.log, max_connections=4)
        self.proxy.start()
    def tearDown(self):
        self.proxy.close(); self.echo.close(); self.tmp.cleanup()

    def connect(self, line, extra=b""):
        s = socket.create_connection(("127.0.0.1", self.proxy.port), timeout=3)
        s.sendall(line.encode() + b"\r\n\r\n" + extra)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = s.recv(1024)
            if not chunk:
                break
            data += chunk
        status = int(data.split(b" ", 2)[1]) if data.startswith(b"HTTP/") else 0
        return s, status

    def status(self, line):
        s, status = self.connect(line)
        s.close()
        return status

class PolicyTests(unittest.TestCase):
    def test_valid_and_invalid_entries(self):
        p = Policy(["API.Example.com", "*.cdn.example.net", "  # x", ""])
        self.assertTrue(p.allows("api.example.com", 443))
        self.assertFalse(p.allows("api.example.com", 80))
        self.assertTrue(p.allows("a.b.cdn.example.net", 443))
        self.assertFalse(p.allows("cdn.example.net", 443))                 # wildcard does not match the bare suffix
        for bad in (["*.com"], ["com"], ["1.2.3.4"], ["0x7f.0.0.1"], ["2130706433"], ["a_b.example.com"], ["-a.example.com"],
                    ["exa mple.com"], ["*.*.example.com"], ["http://example.com"], ["example.com/path"], []):
            with self.assertRaises(PolicyError, msg=bad):
                Policy(bad)
        with self.assertRaises(PolicyError):
            Policy(["example.com"], ports=[0])
        with self.assertRaises(PolicyError):
            Policy(["example.com"], ports=[])

    def test_suffix_boundaries(self):
        p = Policy(["example.com", "*.example.org"])
        for host in ("evil-example.com", "example.com.evil.com", "xexample.org", "example.org.evil.io", "notexample.com"):
            self.assertFalse(p.allows(host, 443), host)
        self.assertTrue(p.allows("a.example.org", 443))

    def test_load_is_strict(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "allow.conf"
            f.write_text("api.example.com\n")
            self.assertTrue(Policy.load(f).allows("api.example.com", 443))
            f.write_text("\n# nothing\n")
            with self.assertRaises(PolicyError):
                Policy.load(f)                                              # an empty list must never become an open proxy
            f.write_text("x" * 20000)
            with self.assertRaises(PolicyError):
                Policy.load(f)
            f.unlink(); os.symlink("/etc/passwd", f)
            with self.assertRaises(PolicyError):
                Policy.load(f)

    def test_ip_literal_detection(self):
        for lit in ("1.2.3.4", "127.0.0.1", "2130706433", "0x7f000001", "0x7f.1", "017700000001", "[::1]", "::1", "fe80::1", "1.2.3", "010.1.1.1"):
            self.assertTrue(is_ip_literal(lit), lit)
        for name in ("api.example.com", "a1.example.com", "example.com", "x-1.example.org"):
            self.assertFalse(is_ip_literal(name), name)

class ProxyTests(Base):
    def test_allowed_destination_tunnels_data_both_ways(self):
        s, status = self.connect("CONNECT api.example.com:443 HTTP/1.1")
        self.assertEqual(status, 200)
        s.sendall(b"hello through the tunnel")
        self.assertEqual(s.recv(100), b"hello through the tunnel")
        s.close()
        time.sleep(0.2)
        self.assertEqual(self.connected, [(PUBLIC, 443)])                    # connected to the address that was validated
        self.assertEqual(self.proxy.stats()["allowed"], 1)

    def test_normalisation_and_wildcards(self):
        self.assertEqual(self.status("CONNECT API.Example.COM.:443 HTTP/1.1"), 200)
        self.assertEqual(self.status("CONNECT x.cdn.example.net:443 HTTP/1.1"), 200)

    def test_everything_else_is_denied(self):
        cases = {
            "GET http://api.example.com/ HTTP/1.1": 405, "POST / HTTP/1.1": 405, "CONNECT api.example.com:80 HTTP/1.1": 403,
            "CONNECT api.example.com:22 HTTP/1.1": 403, "CONNECT evil.example.com:443 HTTP/1.1": 403,
            "CONNECT example.com:443 HTTP/1.1": 403, "CONNECT api.example.com.evil.com:443 HTTP/1.1": 403,
            "CONNECT 93.184.216.34:443 HTTP/1.1": 403, "CONNECT 127.0.0.1:443 HTTP/1.1": 403, "CONNECT 2130706433:443 HTTP/1.1": 403,
            "CONNECT 0x7f.1:443 HTTP/1.1": 403, "CONNECT [::1]:443 HTTP/1.1": 403, "CONNECT localhost:443 HTTP/1.1": 403,
            "CONNECT api.example.com HTTP/1.1": 400, "CONNECT api.example.com:abc HTTP/1.1": 400, "CONNECT": 400, "garbage": 400,
        }
        for line, expected in cases.items():
            self.assertEqual(self.status(line), expected, line)
        self.assertEqual(self.connected, [])                                 # nothing was ever connected upstream
        self.assertEqual(self.proxy.stats()["allowed"], 0)

    def test_dns_rebinding_and_private_resolutions_are_refused(self):
        private = ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.9", "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fc00::1", "fe80::1", "224.0.0.1",
                   "239.255.255.250", "240.0.0.1", "255.255.255.255", "192.0.0.1", "198.18.0.1", "192.0.2.1",
                   "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::ffff:169.254.169.254", "64:ff9b::a00:1", "2002:a00:1::1",
                   "2001:0:4136:e378::1", "ff02::1", "::", "not-an-ip"]
        for address in private:
            self.resolutions["api.example.com"] = [address]
            self.assertEqual(self.status("CONNECT api.example.com:443 HTTP/1.1"), 403, address)
        self.resolutions["api.example.com"] = [PUBLIC, "10.0.0.1"]           # one bad address poisons the answer
        self.assertEqual(self.status("CONNECT api.example.com:443 HTTP/1.1"), 403)
        self.resolutions["api.example.com"] = []
        self.assertEqual(self.status("CONNECT api.example.com:443 HTTP/1.1"), 403)
        del self.resolutions["api.example.com"]
        self.assertEqual(self.status("CONNECT api.example.com:443 HTTP/1.1"), 502)
        self.assertEqual(self.connected, [])
        self.assertGreaterEqual(self.proxy.stats()["deniedByReason"]["non-public-address"], len(private))

    def test_public_addresses_are_accepted(self):
        for address in ("93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "2a00:1450:4001:81b::200e", "::ffff:8.8.8.8"):
            self.assertTrue(ep.is_public_address(address), address)

    def test_oversized_and_slow_handshakes(self):
        s = socket.create_connection(("127.0.0.1", self.proxy.port), timeout=3)
        s.sendall(b"CONNECT api.example.com:443 HTTP/1.1\r\n" + b"X: " + b"a" * 20000 + b"\r\n\r\n")
        self.assertIn(b"431", s.recv(100)); s.close()
        with patch.object(ep, "HANDSHAKE_TIMEOUT", 0.4):
            s = socket.create_connection(("127.0.0.1", self.proxy.port), timeout=3)
            s.sendall(b"CONNECT api.example.com")                              # never finishes: slowloris
            started = time.time()
            data = s.recv(100)
            self.assertLess(time.time() - started, 2.0)
            self.assertTrue(data == b"" or b"431" in data)
            s.close()

    def test_idle_tunnels_are_closed(self):
        with patch.object(ep, "IDLE_TIMEOUT", 0.6):
            s, status = self.connect("CONNECT api.example.com:443 HTTP/1.1")
            self.assertEqual(status, 200)
            s.settimeout(4)
            self.assertEqual(s.recv(10), b"")                                  # closed by the proxy
            s.close()

    def test_connection_cap(self):
        held = [self.connect("CONNECT api.example.com:443 HTTP/1.1")[0] for _ in range(4)]
        self.assertEqual(self.status("CONNECT api.example.com:443 HTTP/1.1"), 503)
        for s in held:
            s.close()
        time.sleep(0.5)
        self.assertEqual(self.status("CONNECT api.example.com:443 HTTP/1.1"), 200)     # capacity is released

    def test_log_has_no_payloads_and_is_bounded(self):
        s, _ = self.connect("CONNECT api.example.com:443 HTTP/1.1")
        s.sendall(b"SECRET-PAYLOAD-AND-TOKEN"); s.recv(100); s.close()
        self.status("CONNECT evil.example.com:443 HTTP/1.1")
        time.sleep(0.3)
        text = self.log.read_text()
        self.assertNotIn("SECRET", text)
        rows = [json.loads(x) for x in text.splitlines()]
        self.assertEqual({(r["host"], r["decision"]) for r in rows}, {("api.example.com", "allowed"), ("evil.example.com", "denied")})
        self.assertTrue(all(set(r) == {"t", "host", "port", "decision", "reason", "bytes"} for r in rows))
        with patch.object(ep, "LOG_LIMIT", 10):
            self.status("CONNECT evil2.example.com:443 HTTP/1.1")
            time.sleep(0.2)
        self.assertNotIn("evil2", self.log.read_text())

class ConstructionTests(unittest.TestCase):
    def test_loopback_only_and_no_open_proxy(self):
        for host in ("0.0.0.0", "::", "192.168.1.5", "localhost"):
            with self.assertRaises(PolicyError):
                EgressProxy(Policy(["example.com"]), host=host, port=0)

    def test_module_has_no_http_forwarding_or_shell(self):
        src = (ROOT / "runtime/aiws_egress_proxy.py").read_text(encoding="utf-8")
        for bad in ("subprocess", "os.system", "urllib", "http.client", "shell=True"):
            self.assertNotIn(bad, src)
        self.assertIn("geteuid", src)                                          # refuses to run as root

if __name__ == "__main__":
    unittest.main()
