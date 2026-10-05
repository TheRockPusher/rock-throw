"""A small, server-rendered notebook backed by SQLite."""

from contextlib import closing
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit


STYLE = """
body { font: 16px system-ui, sans-serif; max-width: 760px; margin: 40px auto;
       padding: 0 20px; color: #253044; background: #fafafa; }
a { color: #2359a8; }
nav { display: flex; gap: 20px; margin-bottom: 24px; }
label { display: block; margin-top: 16px; font-weight: 600; }
input, textarea { box-sizing: border-box; width: 100%; padding: 10px;
                  font: inherit; border: 1px solid #aab2bf; border-radius: 4px; }
textarea { min-height: 220px; }
button { padding: 10px 18px; margin-top: 14px; font: inherit; cursor: pointer; }
li { padding: 10px 0; }
.note-body { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
[role=alert] { color: #a22020; }
small { color: #626c7c; }
"""


def connect():
    connection = sqlite3.connect(os.environ.get("NOTES_DB", "notes.db"))
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(connect()) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def document(title, content):
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} · Notes</title><style>{STYLE}</style></head>"
        '<body><nav><a href="/">All notes</a>'
        '<a href="/notes/new">New note</a></nav>'
        f"<main>{content}</main></body></html>"
    )


def note_list(notes, empty_message):
    if not notes:
        return f"<p>{escape(empty_message)}</p>"
    items = "".join(
        f'<li><a href="/notes/{note["id"]}">{escape(note["title"])}</a></li>'
        for note in notes
    )
    return f"<ul>{items}</ul>"


def search_form(query=""):
    return (
        '<form action="/search" method="get">'
        '<label for="search-query">Search</label>'
        f'<input id="search-query" name="q" value="{escape(query, quote=True)}">'
        '<button type="submit">Search</button></form>'
    )


def editor(title="", body="", error=False):
    alert = '<p role="alert">Title is required</p>' if error else ""
    return (
        f'<h1>New note</h1>{alert}'
        '<form action="/notes" method="post" aria-label="Note editor">'
        '<label for="note-title">Title</label>'
        f'<input id="note-title" name="title" value="{escape(title, quote=True)}">'
        '<label for="note-body">Body</label>'
        f'<textarea id="note-body" name="body">{escape(body)}</textarea>'
        '<button type="submit">Save note</button></form>'
    )


class NotesHandler(BaseHTTPRequestHandler):
    def send_payload(self, payload, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def html(self, title, content, status=200):
        self.send_payload(
            document(title, content).encode("utf-8"),
            "text/html; charset=utf-8", status,
        )

    def json(self, value):
        self.send_payload(
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def not_found(self):
        self.html("Not found", "<h1>Not found</h1><p>This page does not exist.</p>", 404)

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path
        if path == "/healthz":
            self.json({"status": "ok", "version": "1.4.0"})
            return
        if path == "/notes/new":
            self.html("New note", editor())
            return
        if path in ("/", "/search", "/api/notes"):
            query = parse_qs(url.query, keep_blank_values=True).get("q", [""])[0]
            with closing(connect()) as connection:
                if path == "/search":
                    notes = connection.execute(
                        "SELECT * FROM notes WHERE title LIKE ? OR body LIKE ? ORDER BY id DESC",
                        (f"%{query}%", f"%{query}%"),
                    ).fetchall()
                else:
                    notes = connection.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
            if path == "/api/notes":
                self.json([dict(note) for note in notes])
            elif path == "/search":
                self.html("Search", "<h1>Search notes</h1>" + search_form(query)
                          + note_list(notes, "No notes match"))
            else:
                self.html("All notes", "<h1>Notes</h1>" + search_form()
                          + note_list(notes, "No notes yet"))
            return
        match = re.fullmatch(r"/notes/([0-9]+)", path)
        if match:
            with closing(connect()) as connection:
                note = connection.execute(
                    "SELECT * FROM notes WHERE CAST(id AS TEXT) = ?", (match[1],)
                ).fetchone()
            if note is not None:
                self.html(note["title"], (
                    f'<h1>{escape(note["title"])}</h1>'
                    f'<p><small>Created {escape(note["created_at"])}</small></p>'
                    f'<div class="note-body">{escape(note["body"])}</div>'
                    f'<form action="/notes/{note["id"]}/delete" method="post">'
                    '<button type="submit">Delete</button></form>'
                ))
                return
        self.not_found()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/notes":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0:
                    raise ValueError("Negative content length")
            except ValueError:
                self.html("Bad request", "<h1>Invalid request body</h1>", 400)
                return
            fields = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"),
                              keep_blank_values=True)
            title = fields.get("title", [""])[0].strip()
            body = fields.get("body", [""])[0]
            if not title:
                self.html("New note", editor(title, body, error=True), 400)
                return
            with closing(connect()) as connection, connection:
                cursor = connection.execute(
                    "INSERT INTO notes (title, body, created_at) VALUES (?, ?, ?)",
                    (title, body, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
                note_id = cursor.lastrowid
            self.redirect(f"/notes/{note_id}")
            return
        match = re.fullmatch(r"/notes/([0-9]+)/delete", path)
        if match:
            with closing(connect()) as connection, connection:
                cursor = connection.execute(
                    "DELETE FROM notes WHERE CAST(id AS TEXT) = ?", (match[1],)
                )
                deleted = cursor.rowcount
            if deleted:
                self.redirect("/")
                return
        self.not_found()


def main():
    port = int(os.environ.get("PORT", "8000"))
    initialize_database()
    with ThreadingHTTPServer(("127.0.0.1", port), NotesHandler) as server:
        print(f"Notes listening on http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
