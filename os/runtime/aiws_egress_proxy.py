"""Domain-allowlist HTTPS egress proxy for the builder lane (step O4). Standard library only.

The builder CLI runs as its own UID. The kernel firewall (nftables, see os/builder) lets that UID reach
ONLY this proxy on loopback; every other destination is dropped. This proxy then enforces:

  * CONNECT only (no plain HTTP), port 443 only (configurable list), allow-listed host names only;
  * IP literals are refused (decimal/hex/octal tricks included) so the allowlist cannot be bypassed;
  * the proxy resolves the name itself and refuses the connection if ANY resolved address is not a
    public/global address (private, loopback, link-local, metadata endpoint, CGNAT, ULA ...), then
    connects to the resolved address it validated (no second lookup: DNS-rebinding safe);
  * bounded headers, handshake timeout, idle timeout, total tunnel lifetime, byte cap, concurrency cap;
  * binds to 127.0.0.1 only, refuses to run as root, writes a small JSONL log WITHOUT payloads.

It cannot inspect TLS payloads and does not try to: it limits WHERE traffic can go, not WHAT is sent.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import socket
import socketserver
import threading
import time

MAX_HEADER_BYTES = 8192
HANDSHAKE_TIMEOUT = 10.0
IDLE_TIMEOUT = 120.0
MAX_TUNNEL_SECONDS = 3600.0
MAX_TUNNEL_BYTES = 2 * 1024 ** 3
MAX_CONNECTIONS = 16
LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\Z")
LOG_LIMIT = 1024 * 1024

class PolicyError(ValueError):
    pass

def is_ip_literal(host):
    """True for any spelling the OS resolver would treat as an address (dotted, decimal, hex, octal, v6)."""
    if host.startswith("[") or ":" in host:
        return True
    if re.fullmatch(r"(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+)){0,3}", host):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False

class Policy:
    """Allowlist of exact hosts and `*.suffix` wildcards. Wildcards must keep at least two labels."""
    def __init__(self, entries, ports=(443,)):
        self.exact, self.suffixes = set(), set()
        for raw in entries:
            entry = raw.strip().lower()
            if not entry or entry.startswith("#"):
                continue
            wildcard = entry.startswith("*.")
            host = entry[2:] if wildcard else entry
            labels = host.split(".")
            if len(labels) < 2 or any(not LABEL.match(x) for x in labels) or is_ip_literal(host):
                raise PolicyError("Invalid allowlist entry: %r" % raw[:60])
            (self.suffixes if wildcard else self.exact).add(host)
        if not self.exact and not self.suffixes:
            raise PolicyError("The allowlist is empty: refusing to start an open proxy")
        if not ports or any(not isinstance(p, int) or not 1 <= p <= 65535 for p in ports):
            raise PolicyError("Invalid port list")
        self.ports = frozenset(ports)

    @classmethod
    def load(cls, path, ports=(443,)):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
            raise PolicyError("Allowlist must be a regular file up to 16 KiB")
        return cls(path.read_text(encoding="utf-8").splitlines(), ports)

    @classmethod
    def load_with_extra(cls, path, extra_path=None, ports=(443,)):
        """The base allowlist, plus an OPTIONAL second file the owner enables on purpose (e.g. package registries). A missing extra file
        adds nothing; a malformed one stops the proxy rather than being half-applied."""
        base = cls.load(path, ports)
        if extra_path and Path(extra_path).exists():
            extra = cls.load(extra_path, ports)
            base.exact |= extra.exact
            base.suffixes |= extra.suffixes
        return base

    def allows(self, host, port):
        if port not in self.ports:
            return False
        if host in self.exact:
            return True
        return any(host.endswith("." + suffix) for suffix in self.suffixes)

V6_GLOBAL_UNICAST = ipaddress.ip_network("2000::/3")
V6_TUNNELS = tuple(ipaddress.ip_network(n) for n in ("2002::/16", "2001::/32", "2001:db8::/32", "3fff::/20"))

def is_public_address(address):
    """Strictly public unicast only. Python's is_global alone accepts some multicast/tunnel ranges."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped                       # ::ffff:10.0.0.1 is the private address 10.0.0.1
    if (ip.is_multicast or ip.is_reserved or ip.is_unspecified or ip.is_loopback or ip.is_link_local
            or ip.is_private or not ip.is_global):
        return False
    if ip.version == 6:                          # only global unicast, and never a tunnel/transition range
        return ip in V6_GLOBAL_UNICAST and not any(ip in net for net in V6_TUNNELS)
    return True

def default_resolver(host):
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})

def default_connector(address, port, timeout):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((address, port))
    return sock

class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        proxy = self.server.proxy
        if not proxy.slots.acquire(blocking=False):
            self._reply(503, "Busy")
            proxy.record("-", 0, "denied", "too-many-connections")
            return
        try:
            self._serve(proxy)
        except (OSError, ValueError):
            pass
        finally:
            proxy.slots.release()
            try:
                self.request.close()
            except OSError:
                pass

    def _reply(self, status, text):
        try:
            self.request.sendall(("HTTP/1.1 %d %s\r\nConnection: close\r\nContent-Length: 0\r\n\r\n" % (status, text)).encode())
        except OSError:
            pass

    def _read_head(self):
        sock = self.request
        sock.settimeout(HANDSHAKE_TIMEOUT)
        data, deadline = b"", time.monotonic() + HANDSHAKE_TIMEOUT
        while b"\r\n\r\n" not in data:
            if len(data) > MAX_HEADER_BYTES or time.monotonic() > deadline:
                return None
            chunk = sock.recv(2048)
            if not chunk:
                return None
            data += chunk
        head, _, rest = data.partition(b"\r\n\r\n")
        return head, rest

    def _serve(self, proxy):
        got = self._read_head()
        if got is None:
            self._reply(431, "Bad request")
            proxy.record("-", 0, "denied", "bad-handshake")
            return
        head, rest = got
        try:
            first = head.split(b"\r\n", 1)[0].decode("ascii")
            method, target, version = first.split(" ")
        except (UnicodeDecodeError, ValueError):
            self._reply(400, "Bad request")
            proxy.record("-", 0, "denied", "malformed")
            return
        if method != "CONNECT" or not version.startswith("HTTP/1."):
            self._reply(405, "Only CONNECT is supported")
            proxy.record("-", 0, "denied", "method")
            return
        host, sep, port_text = target.rpartition(":")
        if not sep or not port_text.isdigit():
            self._reply(400, "Bad target")
            proxy.record("-", 0, "denied", "bad-target")
            return
        port = int(port_text)
        host = host.lower().rstrip(".")
        if not host or len(host) > 253 or is_ip_literal(host):
            self._reply(403, "IP literals are not allowed")
            proxy.record(host[:80], port, "denied", "ip-literal")
            return
        if not proxy.policy.allows(host, port):
            self._reply(403, "Destination not allowed")
            proxy.record(host[:80], port, "denied", "not-allowlisted")
            return
        try:
            addresses = proxy.resolver(host)
        except OSError:
            self._reply(502, "Cannot resolve")
            proxy.record(host, port, "denied", "resolve-failed")
            return
        if not addresses or any(not self._global(a) for a in addresses):
            self._reply(403, "Resolves to a non-public address")
            proxy.record(host, port, "denied", "non-public-address")
            return
        upstream = None
        for address in addresses[:3]:
            try:
                upstream = proxy.connector(address, port, 10.0)
                break
            except OSError:
                continue
        if upstream is None:
            self._reply(502, "Cannot connect")
            proxy.record(host, port, "denied", "connect-failed")
            return
        try:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            moved = self._splice(self.request, upstream, rest)
        finally:
            upstream.close()
        proxy.record(host, port, "allowed", "ok", moved)

    @staticmethod
    def _global(address):
        return is_public_address(address)

    @staticmethod
    def _splice(client, upstream, initial):
        client.settimeout(None)
        upstream.settimeout(None)
        total, start, last = 0, time.monotonic(), time.monotonic()
        if initial:
            upstream.sendall(initial)
            total += len(initial)
        sockets = [client, upstream]
        while True:
            now = time.monotonic()
            if now - start > MAX_TUNNEL_SECONDS or now - last > IDLE_TIMEOUT or total > MAX_TUNNEL_BYTES:
                break
            readable, _, broken = select.select(sockets, [], sockets, 1.0)
            if broken:
                break
            for source in readable:
                try:
                    chunk = source.recv(65536)
                except OSError:
                    return total
                if not chunk:
                    return total
                target = upstream if source is client else client
                try:
                    target.sendall(chunk)
                except OSError:
                    return total
                total += len(chunk)
                last = now
        return total

class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class EgressProxy:
    def __init__(self, policy, host="127.0.0.1", port=3128, resolver=default_resolver, connector=default_connector,
                 log_path=None, max_connections=MAX_CONNECTIONS):
        if host != "127.0.0.1":
            raise PolicyError("The egress proxy may only bind to 127.0.0.1")
        self.policy, self.resolver, self.connector = policy, resolver, connector
        self.slots = threading.BoundedSemaphore(max_connections)
        self.lock = threading.Lock()
        self.counters = {"allowed": 0, "denied": 0, "bytes": 0}
        self.reasons = {}
        self.log_path = Path(log_path) if log_path else None
        self.server = _Server((host, port), _Handler)
        self.server.proxy = self
        self.port = self.server.server_address[1]

    def record(self, host, port, decision, reason, moved=0):
        with self.lock:
            self.counters[decision] += 1
            self.counters["bytes"] += moved
            if decision == "denied":
                self.reasons[reason] = self.reasons.get(reason, 0) + 1
            if self.log_path is not None:
                try:
                    if self.log_path.is_symlink() or (self.log_path.exists() and self.log_path.stat().st_size > LOG_LIMIT):
                        return
                    with self.log_path.open("a", encoding="utf-8") as stream:     # no payloads, no URLs, no query strings
                        stream.write(json.dumps({"t": int(time.time()), "host": host, "port": port, "decision": decision,
                                                 "reason": reason, "bytes": moved}, separators=(",", ":")) + "\n")
                except OSError:
                    pass

    def stats(self):
        with self.lock:
            return {**self.counters, "deniedByReason": dict(self.reasons)}

    def serve_forever(self):
        self.server.serve_forever(poll_interval=0.2)

    def start(self):
        thread = threading.Thread(target=self.serve_forever, daemon=True, name="aiws-egress")
        thread.start()
        return thread

    def close(self):
        self.server.shutdown()
        self.server.server_close()

def main():
    parser = argparse.ArgumentParser(description="AIWS builder egress allowlist proxy")
    parser.add_argument("--allow", default="/etc/aiws/egress-allow.conf")
    parser.add_argument("--port", type=int, default=3128)
    parser.add_argument("--log", default=None)
    parser.add_argument("--allow-extra", default=None, help="optional second allowlist file (ignored when it does not exist)")
    args = parser.parse_args()
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        parser.error("The egress proxy must not run as root")
    try:
        proxy = EgressProxy(Policy.load_with_extra(args.allow, args.allow_extra), port=args.port, log_path=args.log)
    except PolicyError as exc:
        parser.error(str(exc))
    proxy.serve_forever()

if __name__ == "__main__":
    main()
