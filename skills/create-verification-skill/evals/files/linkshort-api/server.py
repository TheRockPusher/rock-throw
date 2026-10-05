"""Linkshort JSON API and static admin frontend."""

import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import string
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit


ALPHABET = string.ascii_letters + string.digits
CODE_PATTERN = r"[A-Za-z0-9]{6}"


class LinkStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.lock = threading.Lock()
        if self.path.exists():
            self.links = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.links = {}

    def _save(self, links):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", delete=False,
            ) as handle:
                temporary = handle.name
                json.dump(links, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        self.links = links

    def create(self, url):
        with self.lock:
            code = "".join(secrets.choice(ALPHABET) for _ in range(6))
            while code in self.links:
                code = "".join(secrets.choice(ALPHABET) for _ in range(6))
            record = {
                "code": code,
                "url": url,
                "clicks": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save({**self.links, code: record})
            return record.copy()

    def list_links(self):
        with self.lock:
            return [record.copy() for record in self.links.values()]

    def get(self, code, click=False):
        with self.lock:
            record = self.links.get(code)
            if record is None:
                return None
            record = record.copy()
            if click:
                record["clicks"] += 1
                self._save({**self.links, code: record})
            return record

    def delete(self, code):
        with self.lock:
            if code not in self.links:
                return False
            remaining = self.links.copy()
            del remaining[code]
            self._save(remaining)
            return True


def valid_url(value):
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    def json_response(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def not_found(self):
        self.json_response(404, {"error": "not found"})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/links":
            self.not_found()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("empty body")
            payload = json.loads(self.rfile.read(length))
            url = payload.get("url") if isinstance(payload, dict) else None
        except (ValueError, UnicodeDecodeError):
            self.json_response(400, {"error": "invalid url"})
            return
        if not valid_url(url):
            self.json_response(400, {"error": "invalid url"})
            return
        record = self.server.store.create(url)
        self.json_response(201, {
            "code": record["code"],
            "url": record["url"],
            "short_url": f"http://127.0.0.1:{self.server.server_port}/{record['code']}",
        })

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.json_response(200, {"ok": True, "version": "2.1.0"})
        elif path == "/api/links":
            self.json_response(200, self.server.store.list_links())
        elif match := re.fullmatch(rf"/api/links/({CODE_PATTERN})/stats", path):
            record = self.server.store.get(match.group(1))
            if record is None:
                self.not_found()
            else:
                self.json_response(200, record)
        elif path.startswith("/admin/"):
            self.serve_admin(path)
        elif match := re.fullmatch(rf"/({CODE_PATTERN})", path):
            record = self.server.store.get(match.group(1), click=True)
            if record is None:
                self.not_found()
                return
            self.send_response(302)
            self.send_header("Location", record["url"])
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.not_found()

    def do_DELETE(self):
        path = urlsplit(self.path).path
        match = re.fullmatch(rf"/api/links/({CODE_PATTERN})", path)
        if match is None or not self.server.store.delete(match.group(1)):
            self.not_found()
            return
        self.send_response(204)
        self.end_headers()

    def serve_admin(self, path):
        relative = unquote(path[len("/admin/"):]) or "index.html"
        root = self.server.static_dir
        try:
            file_path = (root / relative).resolve()
            if not file_path.is_relative_to(root) or not file_path.is_file():
                self.not_found()
                return
            body = file_path.read_bytes()
        except (OSError, ValueError):
            self.not_found()
            return
        content_type = mimetypes.guess_type(str(file_path))[0]
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    static_dir = Path(__file__).resolve().parent / "static"
    if not static_dir.is_dir():
        print(
            f"fatal: static directory not found at {static_dir} "
            "(build the admin UI first)",
            file=sys.stderr,
            flush=True,
        )
        return 1
    port = int(os.environ.get("LINKSHORT_PORT", "8080"))
    store = LinkStore(os.environ.get("LINKSHORT_DATA", "links.json"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.store = store
    server.static_dir = static_dir
    print(f"linkshort ready on :{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
