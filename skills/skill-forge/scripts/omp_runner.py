# Derived from Anthropic skill-creator (Apache-2.0); modified for OMP.
"""Headless OMP transport, event accounting, and skill-read detection."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import queue
import re
import select
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable
import uuid

OMP_BIN = os.environ.get("SKILL_FORGE_OMP", "omp")
DISCOVERY_PROVIDERS = [
    "native", "skillshare", "omp-managed", "omp-plugins", "claude", "agent-plugins",
    "codex", "agents", "claude-plugins", "gemini", "opencode", "cursor", "windsurf",
    "cline", "github", "vscode", "agents-md", "claude-md", "mcp-json", "ssh-json",
    "builtin-defaults",
]

_process_lock = threading.Lock()
_live_processes: set[subprocess.Popen] = set()
_cancelled = threading.Event()


def _unregister(process):
    with _process_lock:
        _live_processes.discard(process)


def terminate_all():
    """Cancel this runner permanently; terminate/reap all live groups within one grace window."""
    with _process_lock:
        _cancelled.set()
        processes = list(_live_processes)
        for process in processes:
            process._skill_forge_cancelled = True
    for process in processes:
        _signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + 5
    for process in processes:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for process in processes:
        _signal_group(process, signal.SIGKILL)
    for process in processes:
        process.wait()


def isolated_overlay(*, skill_dirs: list[Path] = (), include_skills: list[str] | None = None,
                     skill_commands: bool = False, keep_todo: bool = True, retries: bool = True) -> dict:
    skills = {
        "enabled": bool(skill_dirs), "enableSkillCommands": skill_commands,
        "customDirectories": [str(Path(p).resolve()) for p in skill_dirs],
        "includeSkills": include_skills if include_skills is not None else [],
    }
    for source in ("Pi", "Agents", "Claude"):
        for scope in ("User", "Project"):
            skills[f"enable{source}{scope}"] = False
    skills["enableCodexUser"] = False
    return {
        "disabledProviders": list(DISCOVERY_PROVIDERS), "enabledProviders": [],
        "extensions": [], "autoResume": False, "memory": {"backend": "off"},
        "autolearn": {"enabled": False, "autoContinue": False}, "advisor": {"enabled": False},
        "providers": {"cacheWarming": "off"},
        "retry": {"enabled": retries, "modelFallback": False},
        "todo": {"enabled": keep_todo}, "skills": skills,
    }


def ambient_overlay(*, skill_dirs=(), ignored_skills: list[str] = ()) -> dict:
    return {"skills": {"customDirectories": [str(Path(p).resolve()) for p in skill_dirs],
                       "ignoredSkills": list(ignored_skills)},
            "retry": {"modelFallback": False}}


def write_overlay(path: Path, overlay: dict) -> Path:
    path = Path(path).with_suffix(".yml").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def base_argv(*, cwd: Path, overlay: Path | None, model: str | None, thinking: str | None,
              max_time_s: int, tools: list[str] | None = None, no_tools=False, no_skills=False,
              isolated=True, system_prompt: str | None = None, mode: str = "json",
              approval: str | None = "yolo", no_ui=False) -> list[str]:
    argv = [OMP_BIN, "--cwd", str(Path(cwd).resolve())]
    if overlay is not None:
        argv += ["--config", str(Path(overlay).resolve())]
    argv += ["--no-session", "--no-title"]
    if isolated:
        argv += ["--no-extensions", "--no-rules", "--no-pty"]
    if approval is not None:
        argv += ["--approval-mode", approval]
    argv += ["--max-time", f"{max_time_s}s"]
    if model is not None:
        argv += ["--model", model]
    if thinking is not None:
        argv += ["--thinking", thinking]
    if no_tools:
        argv.append("--no-tools")
    elif tools is not None:
        argv += ["--tools", ",".join(tools)]
    if no_skills:
        argv.append("--no-skills")
    if system_prompt is not None:
        argv += ["--system-prompt", system_prompt, "--append-system-prompt", ""]
    if no_ui:
        argv.append("--no-ui")
    if mode not in ("rpc", "rpc-ui"):
        argv.append("-p")
    argv += ["--mode", mode]
    return argv


@dataclass
class RunResult:
    argv: list[str]
    exit_code: int | None
    outcome: str
    error: str | None
    wall_ms: int
    events: list[dict]
    stderr: str
    stopped_early: bool


_EOF = object()


def _parse_line(line: str) -> dict:
    try:
        value = json.loads(line)
        if isinstance(value, dict):
            return value
    except (ValueError, TypeError):
        pass
    return {"type": "_raw", "text": line.rstrip("\r\n")}


def _read_stdout(stream, frames: queue.Queue, transcript=None):
    try:
        for line in stream:
            if transcript is not None:
                transcript.write(line)
                transcript.flush()
            frames.put(_parse_line(line))
    except Exception as exc:
        frames.put(exc)
    finally:
        stream.close()
        frames.put(_EOF)


def _read_stderr(stream, parts: list[str]):
    try:
        while chunk := stream.read(8192):
            parts.append(chunk)
    finally:
        stream.close()


def _signal_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def _terminate(process) -> int:
    """Terminate all descendants, escalate after five seconds, and reap the leader."""
    _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # A leader can exit while a descendant still holds its stdout/stderr pipe.
        _signal_group(process, signal.SIGKILL)
    return process.wait()


def _start(argv, cwd, env, transcript=None):
    with _process_lock:
        if _cancelled.is_set():
            raise InterruptedError("OMP runner was cancelled")
        process = subprocess.Popen(argv, cwd=str(cwd), env=env, start_new_session=True,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", bufsize=1)
        _live_processes.add(process)
    frames = queue.Queue()
    stderr_parts: list[str] = []
    stdout_thread = threading.Thread(target=_read_stdout,
                                     args=(process.stdout, frames, transcript), daemon=True)
    stderr_thread = threading.Thread(target=_read_stderr, args=(process.stderr, stderr_parts), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    return process, frames, stderr_parts, stdout_thread, stderr_thread


def run_print(prompt: str, argv: list[str], *, cwd: Path, timeout_s: float,
              transcript_path: Path | None = None, stop_when: Callable[[dict], bool] | None = None,
              env: dict | None = None) -> RunResult:
    started = time.monotonic()
    command = list(argv)
    events: list[dict] = []
    outcome, error, stopped = "completed", None, False
    process = None
    transcript = None
    stderr_parts: list[str] = []
    threads = []
    writer_errors = []
    try:
        if transcript_path is not None:
            Path(transcript_path).parent.mkdir(parents=True, exist_ok=True)
            transcript = Path(transcript_path).open("w", encoding="utf-8")
        process, frames, stderr_parts, out_thread, err_thread = _start(command, cwd, env, transcript)
        threads = [out_thread, err_thread]
        def write_prompt():
            try:
                process.stdin.write(prompt)
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                writer_errors.append(str(exc))
            finally:
                process.stdin.close()
        writer = threading.Thread(target=write_prompt, daemon=True)
        writer.start()
        threads.append(writer)
        deadline = started + timeout_s
        ended = False
        while not ended:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome, error = "timeout", f"Hard deadline exceeded ({timeout_s:g}s)"
                _terminate(process)
                break
            try:
                event = frames.get(timeout=remaining)
            except queue.Empty:
                outcome, error = "timeout", f"Hard deadline exceeded ({timeout_s:g}s)"
                _terminate(process)
                break
            if event is _EOF:
                ended = True
            elif isinstance(event, Exception):
                raise event
            else:
                events.append(event)
                if stop_when is not None and stop_when(event):
                    stopped = True
                    _terminate(process)
                    break
        if ended:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                outcome, error = "timeout", f"Hard deadline exceeded ({timeout_s:g}s)"
                _terminate(process)
        for thread in threads:
            thread.join(timeout=5)
        # Include complete events emitted during termination and pipe draining.
        while not frames.empty():
            event = frames.get_nowait()
            if isinstance(event, dict):
                events.append(event)
            elif isinstance(event, Exception) and outcome == "completed":
                outcome, error = "error", str(event)
        if outcome == "completed":
            failed = [m for m in assistant_messages(events) if m.get("stopReason") in ("error", "aborted")]
            if failed:
                outcome = "error"
                error = failed[-1].get("errorMessage") or f"Assistant stopReason: {failed[-1]['stopReason']}"
            elif not stopped and process.returncode != 0:
                outcome, error = "error", f"OMP exited with code {process.returncode}"
            elif writer_errors and not stopped:
                outcome, error = "error", f"Prompt stdin failed: {writer_errors[0]}"
            elif not stopped and not any(e.get("type") == "agent_end" for e in events):
                outcome, error = "error", "OMP exited without an agent_end event"
    except (KeyboardInterrupt, SystemExit):
        outcome, error = "aborted", "Run interrupted"
    except InterruptedError as exc:
        outcome, error = "aborted", str(exc)
    except Exception as exc:
        outcome, error = "error", f"{type(exc).__name__}: {exc}"
    finally:
        if process is not None:
            if process.poll() is None or any(thread.is_alive() for thread in threads):
                _terminate(process)
            else:
                process.wait()
            for thread in threads:
                thread.join(timeout=5)
            _unregister(process)
            if getattr(process, "_skill_forge_cancelled", False):
                outcome, error = "aborted", "Run cancelled"
        if transcript is not None:
            transcript.close()
    return RunResult(command, process.returncode if process is not None else None, outcome,
                     error, round((time.monotonic() - started) * 1000), events,
                     "".join(stderr_parts), stopped)


class RpcSession:
    """A fresh, sequential-command RPC process; completion waits for session settlement."""
    def __init__(self, argv: list[str], *, cwd: Path, timeout_s: float, env=None):
        self.argv = list(argv)
        self.timeout_s = timeout_s
        self._deadline = time.monotonic() + timeout_s
        self.events: list[dict] = []
        self._closed = False
        self._chunks = None
        self.process, self._frames, self._stderr_parts, self._out_thread, self._err_thread = _start(
            self.argv, cwd, env)
        # No buffered stdin writes: non-blocking os.write is deadline-controlled below.
        os.set_blocking(self.process.stdin.fileno(), False)

    @property
    def stderr(self) -> str:
        return "".join(self._stderr_parts)

    def _send(self, command: dict, deadline: float) -> str:
        command = dict(command)
        command.setdefault("id", uuid.uuid4().hex)
        if self._closed:
            raise RuntimeError("RPC session is closed")
        payload = memoryview((json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8"))
        fd = self.process.stdin.fileno()
        while payload:
            if _cancelled.is_set():
                raise InterruptedError("OMP RPC session was cancelled")
            remaining = min(deadline, self._deadline) - time.monotonic()
            if remaining <= 0:
                _terminate(self.process)
                raise TimeoutError("OMP RPC stdin deadline exceeded")
            if not select.select([], [fd], [], remaining)[1]:
                _terminate(self.process)
                raise TimeoutError("OMP RPC stdin deadline exceeded")
            try:
                written = os.write(fd, payload)
            except BlockingIOError:
                continue
            if written == 0:
                raise BrokenPipeError("OMP RPC stdin closed")
            payload = payload[written:]
        return command["id"]

    def _next(self, deadline: float) -> dict:
        while True:
            remaining = min(deadline, self._deadline) - time.monotonic()
            if remaining <= 0:
                _terminate(self.process)
                raise TimeoutError("OMP RPC deadline exceeded")
            try:
                frame = self._frames.get(timeout=remaining)
            except queue.Empty:
                _terminate(self.process)
                raise TimeoutError("OMP RPC deadline exceeded") from None
            if frame is _EOF:
                raise RuntimeError(f"OMP RPC stdout closed (exit={self.process.poll()}): {self.stderr.strip()}")
            if isinstance(frame, Exception):
                raise frame
            if frame.get("type") == "rpc_chunk":
                frame = self._decode_chunk(frame)
                if frame is None:
                    continue
            elif self._chunks is not None:
                raise RuntimeError("Interrupted RPC chunk sequence")
            if frame.get("type") == "rpc_frame_error":
                raise RuntimeError(f"OMP RPC transport error: {frame}")
            if frame.get("type") not in ("response", "ready"):
                self.events.append(frame)
            return frame

    def _decode_chunk(self, frame):
        index, count, size = frame.get("index"), frame.get("count"), frame.get("byteLength")
        if (not isinstance(index, int) or not isinstance(count, int) or not isinstance(size, int)
                or count <= 0 or index < 0 or index >= count or not 0 < size <= 67_108_864
                or not isinstance(frame.get("chunkId"), str)):
            raise RuntimeError("Invalid RPC chunk metadata")
        if self._chunks is None:
            if index != 0:
                raise RuntimeError("RPC chunk sequence did not start at zero")
            self._chunks = {"id": frame["chunkId"], "count": count, "size": size, "parts": [], "bytes": 0}
        chunks = self._chunks
        if (frame["chunkId"] != chunks["id"] or count != chunks["count"]
                or size != chunks["size"] or index != len(chunks["parts"])):
            raise RuntimeError("Interleaved or out-of-order RPC chunks")
        part = base64.b64decode(frame["data"], validate=True)
        chunks["parts"].append(part)
        chunks["bytes"] += len(part)
        if chunks["bytes"] > size:
            raise RuntimeError("RPC chunk payload exceeds declared size")
        if len(chunks["parts"]) < count:
            return None
        if chunks["bytes"] != size:
            raise RuntimeError("RPC chunk byteLength mismatch")
        value = json.loads(b"".join(chunks["parts"]).decode("utf-8"))
        self._chunks = None
        if not isinstance(value, dict):
            raise RuntimeError("RPC logical frame is not an object")
        return value

    def request(self, cmd: dict, *, timeout_s: float) -> dict:
        deadline = time.monotonic() + timeout_s
        request_id = self._send(cmd, deadline)
        while True:
            frame = self._next(deadline)
            if frame.get("type") == "response" and frame.get("id") == request_id:
                return frame

    def prompt(self, message: str, *, timeout_s: float) -> list[dict]:
        deadline = time.monotonic() + timeout_s
        request_id = self._send({"type": "prompt", "message": message}, deadline)
        events = []
        finished = False
        while True:
            frame = self._next(deadline)
            events.append(frame)
            if frame.get("id") == request_id:
                if frame.get("type") == "response":
                    if not frame.get("success", False):
                        raise RuntimeError(frame.get("error", "RPC prompt rejected"))
                    if (frame.get("data") or {}).get("agentInvoked") is False:
                        return events
                elif frame.get("type") == "prompt_result":
                    if frame.get("status") not in ("completed", "failed", "error", "aborted"):
                        raise RuntimeError(f"Unknown RPC prompt status: {frame.get('status')}")
                    finished = True
                    if frame.get("sessionSettled") is True:
                        return events
            if finished and frame.get("type") == "session_settled":
                return events

    def close(self) -> int | None:
        if self._closed:
            return self.process.returncode
        self._closed = True
        try:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            # The reader keeps draining even after EOF on stdin, avoiding backpressure deadlocks.
            try:
                self.process.wait(timeout=max(0, min(5, self._deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                _terminate(self.process)
            if self._out_thread.is_alive():
                self._out_thread.join(timeout=5)
            if self._out_thread.is_alive() or self._err_thread.is_alive():
                _terminate(self.process)
            self._out_thread.join(timeout=5)
            self._err_thread.join(timeout=5)
            while not self._frames.empty():
                frame = self._frames.get_nowait()
                if isinstance(frame, dict):
                    if frame.get("type") == "rpc_chunk":
                        frame = self._decode_chunk(frame)
                    if frame is not None and frame.get("type") not in ("response", "ready"):
                        self.events.append(frame)
            return self.process.wait()
        finally:
            if self.process.poll() is None:
                _terminate(self.process)
            _unregister(self.process)


def assistant_messages(events) -> list[dict]:
    return [e["message"] for e in events if e.get("type") == "message_end"
            and isinstance(e.get("message"), dict) and e["message"].get("role") == "assistant"]


def usage_summary(events) -> dict:
    messages = assistant_messages(events)
    def total(values):
        return sum(values) if values and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                            for v in values) else None
    fields = {"total_tokens": "totalTokens", "input_tokens": "input", "output_tokens": "output",
              "cache_read_tokens": "cacheRead", "cache_write_tokens": "cacheWrite"}
    result = {key: total([(m.get("usage") or {}).get(field) for m in messages])
              for key, field in fields.items()}
    result["cost_usd"] = total([((m.get("usage") or {}).get("cost") or {}).get("total") for m in messages])
    result["requests"] = len(messages) if messages else None
    result["model_time_ms"] = total([m.get("duration") for m in messages])
    return result


def resolved_models(events) -> list[str]:
    models = []
    for message in assistant_messages(events):
        if message.get("provider") and message.get("model"):
            name = f"{message['provider']}/{message['model']}"
            if name not in models:
                models.append(name)
    return models


def tool_calls(events) -> list[dict]:
    calls: dict[str, dict] = {}
    def add(call_id, name, args, is_error=None):
        key = str(call_id) if call_id is not None else "anonymous-" + str(len(calls))
        call = calls.setdefault(key, {"id": call_id, "name": name, "args": args or {}, "is_error": None})
        if name is not None:
            call["name"] = name
        if args is not None:
            call["args"] = args
        if is_error is not None:
            call["is_error"] = bool(is_error)
    # Execution records are canonical, with message content as a fallback per call id.
    for event in events:
        if event.get("type") == "tool_execution_start":
            add(event.get("toolCallId"), event.get("toolName"), event.get("args"))
        elif event.get("type") == "tool_execution_end":
            add(event.get("toolCallId"), event.get("toolName"), None, event.get("isError"))
    for message in assistant_messages(events):
        for block in message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "toolCall" and str(block.get("id")) not in calls:
                add(block.get("id"), block.get("name"), block.get("arguments"))
    for event in events:
        if event.get("type") == "message_update":
            update = event.get("assistantMessageEvent") or {}
            block = update.get("toolCall") or {}
            if update.get("type") == "toolcall_end" and block:
                if block.get("id") is not None and str(block["id"]) in calls:
                    continue
                if block.get("id") is None and any(c["name"] == block.get("name") and c["args"] == block.get("arguments", {}) for c in calls.values()):
                    continue
                add(block.get("id"), block.get("name"), block.get("arguments"))
    return list(calls.values())


def _message_text(message):
    content = message.get("content", [])
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def final_text(events) -> str:
    messages = assistant_messages(events)
    return _message_text(messages[-1]) if messages else ""


def render_transcript_md(events, *, max_result_chars=2000) -> str:
    lines = ["# Executor transcript", ""]
    rendered_calls = set()
    for event in events:
        if event.get("type") == "message_end":
            message = event.get("message", {})
            if message.get("role") in ("user", "assistant"):
                text = _message_text(message)
                if text:
                    lines += [f"## {message['role'].capitalize()}", "", text, ""]
                for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
                    if isinstance(block, dict) and block.get("type") == "toolCall":
                        key = block.get("id")
                        if key not in rendered_calls:
                            rendered_calls.add(key)
                            lines += [f"### Tool: {block.get('name')}", "", "```json",
                                      json.dumps(block.get("arguments", {}), indent=2, ensure_ascii=False), "```", ""]
        elif event.get("type") == "tool_execution_start":
            key = event.get("toolCallId")
            if key not in rendered_calls:
                rendered_calls.add(key)
                lines += [f"### Tool: {event.get('toolName')}", "", "```json",
                          json.dumps(event.get("args", {}), indent=2, ensure_ascii=False), "```", ""]
        elif event.get("type") == "tool_execution_end":
            parts = (event.get("result") or {}).get("content", [])
            text = "\n".join(part.get("text", "") if part.get("type") == "text"
                             else f"[{part.get('type', 'non-text')}]"
                             for part in parts if isinstance(part, dict))
            if len(text) > max_result_chars:
                text = text[:max_result_chars] + "\n[Result truncated; see transcript.jsonl]"
            lines += [f"#### Result: {event.get('toolName')} (error={event.get('isError')})", "", "```text", text, "```", ""]
        elif event.get("type") == "_raw":
            lines += ["### Raw stdout", "", event.get("text", ""), ""]
    lines += ["## Final answer", "", final_text(events), "", "## Usage", "", "```json",
              json.dumps(usage_summary(events), indent=2), "```", ""]
    return "\n".join(lines)


def skill_invocation_message(name: str, body: str, base_dir: Path, user_args: str) -> str:
    return (f'---\n\n[IMPORTANT: User invoked the "{name}" skill; follow its instructions. Full skill below.]\n\n'
            f'{body}\n\n---\n\n[Skill directory: {base_dir}]\n'
            'Resolve relative paths in this skill (e.g. `scripts/foo.js`, `templates/config.yaml`) against this absolute directory; '
            'read referenced assets and templates; run scripts with the terminal tool when skill instructions call for it.\n'
            f'User: {user_args}\n')


_SELECTOR = re.compile(r":(?:raw|img|conflicts|\d+(?:[-+]\d*)?(?:,\d+(?:[-+]\d*)?)*|-\d+|\d+[hms]|\d+:\d+(?::\d+)?)(?=:|$)")


def _strip_selector(path: str) -> str:
    match = _SELECTOR.search(path)
    return path[:match.start()] if match else path


def read_targets(events, *, skill_name: str, skill_md: Path) -> list[dict]:
    skill_md = Path(skill_md).resolve()
    matches = []
    def add(path, is_error):
        if not isinstance(path, str):
            return
        target = _strip_selector(path)
        same = target in (f"skill://{skill_name}", f"skill://{skill_name}/SKILL.md")
        if not same and "://" not in target:
            same = Path(target).expanduser().resolve() == skill_md
        item = {"path": path, "is_error": is_error}
        if same and item not in matches:
            matches.append(item)
    for call in tool_calls(events):
        if call["name"] == "read" and isinstance(call["args"], dict):
            add(call["args"].get("path"), call["is_error"])
    for event in events:
        if event.get("type") == "tool_execution_end" and event.get("toolName") == "read":
            details = (event.get("result") or {}).get("details") or {}
            add(details.get("resolvedPath"), event.get("isError"))
    return matches


def parse_skills_block(system_prompt: str) -> dict[str, str]:
    if isinstance(system_prompt, list):
        system_prompt = "\n".join(system_prompt)
    result = {}
    for block in re.findall(r"<skills>\s*(.*?)\s*</skills>", system_prompt, re.DOTALL):
        for line in block.splitlines():
            match = re.match(r"\s*-\s+([^:\s]+):\s*(.*)", line)
            if match:
                result[match[1]] = match[2].strip()
    return result
