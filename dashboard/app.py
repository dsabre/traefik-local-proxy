#!/usr/bin/env python3
import json
import os
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DOMAINS_FILE = Path(os.environ.get("DOMAINS_FILE", "/config/domains.txt"))
TRAEFIK_HOST = os.environ.get("TRAEFIK_HOST", "traefik")
TRAEFIK_PORT = int(os.environ.get("TRAEFIK_PORT", "443"))
APP_TITLE = os.environ.get("APP_TITLE", "Local Projects")
TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "2"))
HIDE = {h.strip().lower() for h in os.environ.get("HIDE_DOMAINS", "localhost").split(",") if h.strip()}

BASE = Path(__file__).parent
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
ROUTE_RE = re.compile(r"^/\S*$")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # connessione interna verso Traefik


def parse_routes(field):
    routes = []
    for item in field.split(","):
        path, _, label = item.strip().partition(" ")
        if ROUTE_RE.match(path):
            routes.append((path, label.strip() or path))
    return routes


def parse_dir(field):
    if field and len(field) <= 512 and field[0] in "/~" and field.isprintable():
        return field
    return None


def read_lines(path):
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def derive(domain):
    base = domain[: -len(".localhost")] if domain.endswith(".localhost") else domain
    first, *rest = base.split(".")
    name = first.replace("-", " ").replace("_", " ").title()
    label = ".".join(rest) or None
    return name, label


def probe(domain):
    start = time.monotonic()
    try:
        with socket.create_connection((TRAEFIK_HOST, TRAEFIK_PORT), timeout=TIMEOUT) as s:
            with CTX.wrap_socket(s, server_hostname=domain) as tls:
                tls.settimeout(TIMEOUT)
                req = (
                    f"GET / HTTP/1.1\r\nHost: {domain}\r\n"
                    "User-Agent: local-dashboard\r\nAccept: */*\r\nConnection: close\r\n\r\n"
                )
                tls.sendall(req.encode())
                data = b""
                while len(data) < 4096:
                    chunk = tls.recv(4096 - len(data))
                    if not chunk:
                        break
                    data += chunk
    except OSError:
        return {"state": "unknown", "ms": None}

    head, _, body = data.partition(b"\r\n\r\n")
    try:
        code = int(head.split(b" ", 2)[1])
    except (IndexError, ValueError):
        return {"state": "unknown", "ms": None}

    ms = round((time.monotonic() - start) * 1000)
    if code == 404 and body.strip() == b"404 page not found":
        return {"state": "offline", "ms": ms}
    if code in (502, 503, 504):
        return {"state": "error", "ms": ms}
    return {"state": "online", "ms": ms}


def proxy_up():
    try:
        socket.create_connection((TRAEFIK_HOST, TRAEFIK_PORT), timeout=TIMEOUT).close()
        return True
    except OSError:
        return False


def read_entries():
    seen, entries = set(), []
    for line in read_lines(DOMAINS_FILE):
        parts = [p.strip() for p in line.split("|")]
        d = parts[0].lower()
        if not d or d in seen or d in HIDE or "*" in d or not HOST_RE.match(d):
            continue
        seen.add(d)
        name = parts[1] if len(parts) > 1 and parts[1] else None
        label = parts[2] if len(parts) > 2 and parts[2] else None
        routes = parse_routes(parts[3]) if len(parts) > 3 else []
        directory = parse_dir(parts[4]) if len(parts) > 4 else None
        entries.append((d, name, label, routes, directory))
    return entries


def build_payload():
    try:
        entries = read_entries()
    except (OSError, UnicodeDecodeError):
        return {"title": APP_TITLE, "error": "Impossibile leggere la configurazione dei domini.", "projects": [], "proxy": proxy_up()}

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(probe, [e[0] for e in entries]))

    projects = []
    for (d, name, label, routes, directory), r in zip(entries, results):
        auto_name, auto_label = derive(d)
        projects.append({
            "domain": d,
            "name": name or auto_name,
            "label": label or auto_label,
            "url": f"https://{d}",
            "routes": [{"label": l, "url": f"https://{d}{p}"} for p, l in routes],
            "dir": directory,
            **r,
        })
    return {"title": APP_TITLE, "error": None, "projects": projects, "proxy": proxy_up(), "ts": int(time.time())}


class Handler(BaseHTTPRequestHandler):
    server_version = "dashboard"

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/projects":
            return self._send(200, json.dumps(build_payload()).encode(), "application/json")
        if path == "/healthz":
            return self._send(200, b"ok", "text/plain")
        if path in STATIC:
            fname, ctype = STATIC[path]
            return self._send(200, (BASE / fname).read_bytes(), ctype)
        self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
