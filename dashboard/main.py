import html
import json
import os
import socket
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

DOMAINS_FILE = os.getenv("DOMAINS_FILE", "/config/domains.txt")
PROJECTS_FILE = os.getenv("PROJECTS_FILE", "/config/projects.txt")
TRAEFIK_HOST = os.getenv("TRAEFIK_HOST", "traefik")
TRAEFIK_PORT = int(os.getenv("TRAEFIK_PORT", "443"))
APP_TITLE = os.getenv("APP_TITLE", "Local Projects")
PORT = int(os.getenv("PORT", "8000"))


def read_simple_domains(path):
    domains = []

    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].strip()
                if line:
                    domains.append(line)
    except OSError:
        return None

    return domains


def read_project_metadata(path):
    metadata = {}

    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()

                if not line or line.startswith("#"):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if not parts or not parts[0]:
                    continue

                links = []

                if len(parts) > 4 and parts[4]:
                    for item in parts[4].split(","):
                        if "::" not in item:
                            continue

                        label, path_value = item.split("::", 1)
                        label = label.strip()
                        path_value = path_value.strip()

                        if not label or not path_value:
                            continue

                        if not path_value.startswith("/"):
                            path_value = "/" + path_value

                        links.append(
                            {
                                "label": label,
                                "path": path_value,
                                "url": f"https://{parts[0]}{path_value}",
                            }
                        )

                metadata[parts[0]] = {
                    "label": parts[1] if len(parts) > 1 and parts[1] else "",
                    "category": parts[2] if len(parts) > 2 and parts[2] else "",
                    "health_url": parts[3] if len(parts) > 3 and parts[3] else "",
                    "links": links,
                }
    except OSError:
        pass

    return metadata


def humanize_domain(domain):
    name = domain.split(".")[0]
    name = name.replace("-", " ").replace("_", " ")
    return name[:1].upper() + name[1:]


def load_projects():
    domains = read_simple_domains(DOMAINS_FILE)

    if domains is None:
        return None, "Impossibile leggere l'elenco dei domini."

    metadata = read_project_metadata(PROJECTS_FILE)
    projects = []

    for domain in domains:
        extra = metadata.get(domain, {})
        projects.append(
            {
                "domain": domain,
                "label": extra.get("label") or humanize_domain(domain),
                "category": extra.get("category", ""),
                "health_url": extra.get("health_url", ""),
                "links": extra.get("links", []),
            }
        )

    return projects, ""


def check_internal(health_url):
    try:
        with urlopen(Request(health_url, method="GET"), timeout=2) as response:
            return "online" if response.status < 400 else "degraded"
    except HTTPError as e:
        return "offline" if e.code in (502, 504) else "degraded"
    except (URLError, TimeoutError, OSError):
        return "offline"


def check_via_traefik(domain):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((TRAEFIK_HOST, TRAEFIK_PORT), timeout=2) as raw:
            with context.wrap_socket(raw, server_hostname=domain) as tls:
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {domain}\r\n"
                    "Connection: close\r\n"
                    "User-Agent: local-dashboard/1.0\r\n"
                    "\r\n"
                )
                tls.sendall(request.encode())

                response = b""
                while len(response) < 4096:
                    chunk = tls.recv(4096)
                    if not chunk:
                        break
                    response += chunk

                first_line = response.split(b"\r\n", 1)[0].decode(errors="replace")

                if " 502 " in first_line or " 504 " in first_line:
                    return "offline"
                if "HTTP/" in first_line:
                    return "online"
                return "unknown"

    except (socket.timeout, OSError, ssl.SSLError):
        return "unknown"


def status_for(project):
    if project["health_url"]:
        return check_internal(project["health_url"])
    return check_via_traefik(project["domain"])


def render_page():
    projects, error = load_projects()

    if error:
        body = f'<div class="error">{html.escape(error)}</div>'
    elif not projects:
        body = '<div class="empty">Nessun dominio configurato.</div>'
    else:
        cards = []

        for project in projects:
            links_html = ""

            if project["links"]:
                items = "".join(
                    f'<a href="{html.escape(link["url"])}" target="_blank" rel="noopener">'
                    f'{html.escape(link["label"])}</a>'
                    for link in project["links"]
                )
                links_html = f'<div class="links">{items}</div>'

            category = (
                f'<div class="tag">{html.escape(project["category"])}</div>'
                if project["category"]
                else ""
            )

            cards.append(
                f"""
                <a class="card" href="https://{html.escape(project['domain'])}" target="_blank" rel="noopener">
                  <div class="card-top">
                    <span class="project-name">{html.escape(project['label'])}</span>
                    <span class="status" data-status="{status_for(project)}"></span>
                  </div>
                  <div class="domain">{html.escape(project['domain'])}</div>
                  {links_html}
                  {category}
                </a>
                """
            )

        body = f'<div class="grid">{"".join(cards)}</div>'

    return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(APP_TITLE)}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{html.escape(APP_TITLE)}</h1>
        <p>Progetti locali dietro Traefik</p>
      </div>
      <div class="proxy">
        <span class="status" data-status="online"></span>
        Traefik
      </div>
    </header>
    {body}
  </main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_body(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            if self.path == "/static/style.css":
                try:
                    with open("/app/static/style.css", "rb") as f:
                        content = f.read()
                    self.send_body(content, "text/css; charset=utf-8")
                except OSError:
                    self.send_error(404)
                return

            if self.path == "/api/status":
                projects, error = load_projects()
                payload = [] if error else [
                    {"domain": p["domain"], "status": status_for(p)}
                    for p in projects
                ]

                self.send_body(
                    json.dumps(payload).encode(),
                    "application/json",
                )
                return

            self.send_body(render_page().encode(), "text/html; charset=utf-8")

        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
