# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Serve or export an OMP evaluation review or trigger-eval editor."""

import argparse
import base64
import ipaddress
import json
import mimetypes
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from aggregate_benchmark import atomic_write, load_json

MAX_FILE = 10 * 1024 * 1024
MAX_BODY = 5 * 1024 * 1024
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def validate_trigger_evals(value):
    if not isinstance(value, list):
        raise ValueError("Trigger evals must be an array")
    labels, ids, result = {}, set(), []
    for index, item in enumerate(value, 1):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("query"), str)
            or not item["query"].strip()
            or type(item.get("should_trigger")) is not bool
        ):
            raise ValueError("Each trigger eval needs a nonempty query and boolean should_trigger")
        identifier = item.get("id", index)
        if type(identifier) is not int or identifier in ids:
            raise ValueError("Trigger eval IDs must be unique integers")
        ids.add(identifier)
        if item["query"] in labels and labels[item["query"]] != item["should_trigger"]:
            raise ValueError("Duplicate queries have conflicting labels")
        labels[item["query"]] = item["should_trigger"]
        result.append(
            dict(id=identifier, query=item["query"], should_trigger=item["should_trigger"])
        )
    return result


def validate_feedback(value, run_ids):
    if (
        not isinstance(value, dict)
        or value.get("status") not in {"in_progress", "complete"}
        or not isinstance(value.get("reviews"), list)
    ):
        raise ValueError("Feedback requires status and reviews")

    def timestamp(text):
        if not isinstance(text, str):
            raise ValueError("Timestamp must be an ISO string")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid ISO timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        return text

    reviews, seen = [], set()
    for item in value["reviews"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("run_id"), str)
            or item["run_id"] not in run_ids
            or item["run_id"] in seen
            or not isinstance(item.get("feedback"), str)
            or type(item.get("visited")) is not bool
        ):
            raise ValueError("Invalid or duplicate run review")
        seen.add(item["run_id"])
        reviews.append(
            dict(
                run_id=item["run_id"],
                feedback=item["feedback"],
                visited=item["visited"],
                timestamp=timestamp(item.get("timestamp")),
            )
        )
    if value["status"] == "complete" and (
        seen != run_ids or not all(r["visited"] for r in reviews)
    ):
        raise ValueError("Visit every run before completing review")
    return dict(
        status=value["status"], updated_at=timestamp(value.get("updated_at")), reviews=reviews
    )


def embed_file(path, root, prefix, static):
    relative = path.relative_to(root).as_posix()
    item = dict(
        name=path.name,
        path=relative,
        mime=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )
    item["download"] = None if static else "/files/" + prefix + "/" + quote(relative, safe="/")
    if path.stat().st_size > MAX_FILE:
        return dict(
            item,
            type="skipped",
            note="File exceeds 10 MB; not embedded. "
            + ("Open the original file on disk." if static else "Use the download link."),
        )
    raw = path.read_bytes()
    extension = path.suffix.lower()
    if extension in {
        ".txt",
        ".md",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".py",
        ".sh",
        ".log",
        ".svg",
    }:
        item.update(type="text", content=raw.decode("utf-8", errors="replace"))
    else:
        encoded = base64.b64encode(raw).decode("ascii")
        uri = f"data:{item['mime']};base64,{encoded}"
        item.update(
            type="image"
            if extension in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
            else "pdf"
            if extension == ".pdf"
            else "xlsx"
            if extension == ".xlsx"
            else "binary",
            data_uri=uri,
        )
        if extension == ".xlsx":
            item["data_b64"] = encoded
        item["download"] = uri
    if static and item["type"] == "text":
        item["download"] = (
            "data:" + item["mime"] + ";base64," + base64.b64encode(raw).decode("ascii")
        )
    return item


def find_runs(root, prefix="current", static=False):
    runs = []
    for directory in sorted(root.glob("eval-*/*/run-*")):
        if not directory.is_dir():
            continue
        metadata = load_json(directory.parent.parent / "eval_metadata.json", {})
        run = load_json(directory / "run.json", {})
        outputs = []
        output_dir = directory / "outputs"
        if output_dir.is_dir():
            for path in sorted(output_dir.rglob("*")):
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
                    item = embed_file(path, root, prefix, static)
                    item["name"] = path.relative_to(output_dir).as_posix()
                    outputs.append(item)
        transcript = directory / "transcript.md"
        transcript_text = (
            transcript.read_text(encoding="utf-8", errors="replace")
            if transcript.exists() and transcript.stat().st_size <= MAX_FILE
            else "Transcript absent or exceeds 10 MB; open transcript.md on disk."
        )
        runs.append(
            dict(
                id=directory.relative_to(root).as_posix(),
                eval_id=metadata.get("eval_id", run.get("eval_id")),
                eval_name=metadata.get("eval_name", run.get("eval_name")),
                configuration=directory.parent.name,
                prompt=metadata.get("prompt", "No prompt found"),
                expected_output=metadata.get("expected_output", ""),
                assertions=metadata.get("assertions", metadata.get("expectations", [])),
                outputs=outputs,
                transcript=transcript_text,
                run=run,
                timing=load_json(directory / "timing.json", {}),
                grading=load_json(directory / "grading.json"),
            )
        )
    return runs


def script_json(value):
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render(args, static=False):
    if args.trigger_evals:
        data = dict(
            mode="trigger",
            static=static,
            skill_name=args.skill_name or "",
            description=args.description,
            evals=validate_trigger_evals(load_json(args.trigger_evals, [])),
        )
        template = "trigger_review.html"
    else:
        runs = find_runs(args.iteration, static=static)
        previous = {}
        if args.previous:
            feedback = load_json(args.previous / "feedback.json", {}).get("reviews", [])
            by_id = {r["run_id"]: r for r in feedback}
            previous = {
                r["id"]: dict(outputs=r["outputs"], feedback=by_id.get(r["id"]))
                for r in find_runs(args.previous, "previous", static)
            }
        benchmark = load_json(args.benchmark or args.iteration / "benchmark.json")
        data = dict(
            mode="review",
            static=static,
            skill_name=args.skill_name
            or (benchmark or {}).get("metadata", {}).get("skill_name")
            or args.iteration.parent.name,
            runs=runs,
            feedback=load_json(args.iteration / "feedback.json", {}),
            previous=previous,
            benchmark=benchmark,
        )
        template = "viewer.html"
    return (
        (ASSETS / template).read_text(encoding="utf-8").replace("/*__DATA__*/", script_json(data))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iteration", nargs="?", type=Path)
    parser.add_argument("--skill-name")
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--trigger-evals", type=Path)
    parser.add_argument("--description", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--static", type=Path)
    args = parser.parse_args()
    try:
        if bool(args.iteration) == bool(args.trigger_evals):
            raise ValueError("Specify an iteration directory or --trigger-evals, not both")
        for name in ("iteration", "trigger_evals", "benchmark", "previous", "static"):
            if getattr(args, name):
                setattr(args, name, getattr(args, name).resolve())
        if args.iteration and not args.iteration.is_dir():
            raise ValueError("Iteration directory does not exist")
        if args.trigger_evals and not args.skill_name:
            raise ValueError("Trigger editor requires --skill-name")
        if args.static:
            atomic_write(args.static, render(args, True))
            return 0
        if args.host != "localhost" and not ipaddress.ip_address(args.host).is_loopback:
            raise ValueError("Review server must bind a loopback address")
        port = args.port if args.port is not None else (3118 if args.trigger_evals else 3117)
        target = args.trigger_evals or args.iteration / "feedback.json"
        endpoint = "/api/trigger-evals" if args.trigger_evals else "/api/feedback"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *values):
                pass

            def send(self, status, content, mime="application/json"):
                raw = content.encode("utf-8") if isinstance(content, str) else content
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                try:
                    path = urlsplit(self.path).path
                    if path == "/":
                        self.send(200, render(args), "text/html; charset=utf-8")
                    elif path == endpoint:
                        value = load_json(target, [] if args.trigger_evals else {})
                        if args.trigger_evals:
                            value = validate_trigger_evals(value)
                        self.send(200, json.dumps(value, ensure_ascii=False))
                    elif path.startswith("/files/") and args.iteration:
                        parts = unquote(path).split("/", 3)
                        root = (
                            args.iteration
                            if parts[2] == "current"
                            else args.previous
                            if parts[2] == "previous"
                            else None
                        )
                        file = (root / parts[3]).resolve() if root and len(parts) == 4 else None
                        if not file or not file.is_relative_to(root) or not file.is_file():
                            self.send(404, "{}")
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header(
                            "Content-Disposition",
                            "attachment; filename*=UTF-8''" + quote(file.name),
                        )
                        self.send_header("Content-Length", str(file.stat().st_size))
                        self.end_headers()
                        with file.open("rb") as stream:
                            while chunk := stream.read(65536):
                                self.wfile.write(chunk)
                    else:
                        self.send(404, "{}")
                except (OSError, ValueError, TypeError) as exc:
                    self.send(500, json.dumps(dict(error=str(exc))))

            def do_POST(self):
                try:
                    if urlsplit(self.path).path != endpoint:
                        self.send(404, "{}")
                        return
                    origin = self.headers.get("Origin")
                    expected = f"http://{self.headers.get('Host')}"
                    if origin and origin != expected:
                        self.send(403, '{"error":"Cross-origin request rejected"}')
                        return
                    if (
                        self.headers.get("Content-Type", "").split(";", 1)[0].strip()
                        != "application/json"
                    ):
                        raise ValueError("Expected application/json")
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > MAX_BODY:
                        raise ValueError("Request body must be between 1 byte and 5 MB")
                    value = json.loads(self.rfile.read(size))
                    value = (
                        validate_trigger_evals(value)
                        if args.trigger_evals
                        else validate_feedback(
                            value,
                            {
                                p.relative_to(args.iteration).as_posix()
                                for p in args.iteration.glob("eval-*/*/run-*")
                                if p.is_dir()
                            },
                        )
                    )
                    atomic_write(
                        target,
                        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    )
                    self.send(200, '{"ok":true}')
                except (ValueError, TypeError, KeyError) as exc:
                    self.send(400, json.dumps(dict(error=str(exc))))
                except OSError as exc:
                    self.send(500, json.dumps(dict(error=str(exc))))

        render(args)  # Fail before announcing readiness if source data is invalid.
        server = HTTPServer((args.host, port), Handler)
        print(f"Serving at http://{args.host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
