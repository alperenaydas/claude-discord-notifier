#!/usr/bin/env python3
"""Claude Code hook dispatcher for delayed Discord notifications.

Invoked as:
  - Hook mode: stdin = Claude hook JSON, env CLAUDE_NOTIFIER_EVENT in
      {Notification, Stop, UserPromptSubmit, PreToolUse, PostToolUse}
  - Worker mode: `notifier.py --worker <session_id>` — sleeps delay_seconds,
      then sends the pending notification for that session (if not cancelled).
  - CLI mode: `notifier.py --enable | --disable | --status` — opt-in per cwd.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
STATE_DIR = HERE / "state"
PENDING_DIR = STATE_DIR / "pending"
ENABLED_DIR = STATE_DIR / "enabled"
MUTE_SENTINEL = STATE_DIR / "mute_next"
LOG_FILE = HERE / "logs" / "notifier.log"
CONFIG_PATH = HERE / "config.json"

SCHEDULING_EVENTS = {"Notification", "Stop"}
CANCELLING_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse"}


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOG_FILE.open("a") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        log(f"config load failed: {e}")
        return {}


def pending_path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:80] or "unknown"
    return PENDING_DIR / f"{safe}.json"


def cwd_marker_path(cwd: str) -> Path:
    abs_cwd = os.path.abspath(cwd or ".")
    h = hashlib.sha1(abs_cwd.encode("utf-8")).hexdigest()[:16]
    return ENABLED_DIR / h


def is_enabled(cwd: str) -> bool:
    return cwd_marker_path(cwd).exists()


def sweep_stale(stale_after: int) -> None:
    if not PENDING_DIR.exists():
        return
    now = time.time()
    for p in PENDING_DIR.iterdir():
        try:
            if now - p.stat().st_mtime > stale_after:
                p.unlink(missing_ok=True)
                log(f"swept stale {p.name}")
        except Exception:
            pass


def spawn_worker(session_id: str) -> None:
    # Double-fork detach so Claude's hook call returns immediately.
    try:
        if os.fork() != 0:
            os.wait()
            return
    except OSError:
        return
    os.setsid()
    try:
        if os.fork() != 0:
            os._exit(0)
    except OSError:
        os._exit(0)
    # grandchild
    try:
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
    except Exception:
        pass
    os.execv(sys.executable, [sys.executable, str(Path(__file__)), "--worker", session_id])


def read_last_assistant_text(transcript_path: str | None, limit: int = 500) -> str:
    if not transcript_path:
        return ""
    try:
        p = Path(transcript_path)
        if not p.exists():
            return ""
        last = ""
        with p.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                # Claude Code transcript entries typically have {"type": "assistant", "message": {"content": [...]}}
                if entry.get("type") == "assistant":
                    msg = entry.get("message", {})
                    content = msg.get("content", [])
                    parts: list[str] = []
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                parts.append(c.get("text", ""))
                    text = "\n".join(p for p in parts if p).strip()
                    if text:
                        last = text
        if len(last) > limit:
            last = last[:limit].rstrip() + "…"
        return last
    except Exception as e:
        log(f"transcript read failed: {e}")
        return ""


def handle_hook() -> None:
    event = os.environ.get("CLAUDE_NOTIFIER_EVENT", "")
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    cfg = load_config()
    sweep_stale(int(cfg.get("stale_after_seconds", 600)))

    session_id = str(payload.get("session_id") or "unknown")

    if event in CANCELLING_EVENTS:
        p = pending_path(session_id)
        if p.exists():
            p.unlink(missing_ok=True)
            log(f"cancelled pending for {session_id} via {event}")
        return

    if event not in SCHEDULING_EVENTS:
        return

    cwd = payload.get("cwd") or os.getcwd()
    if not is_enabled(cwd):
        log(f"skipped {event} for {session_id}: notifications disabled in {cwd}")
        return

    kind = "await" if event == "Notification" else "done"
    delay = int(cfg.get("delay_seconds", 60))
    record = {
        "kind": kind,
        "event": event,
        "session_id": session_id,
        "cwd": payload.get("cwd", ""),
        "transcript_path": payload.get("transcript_path", ""),
        "message": payload.get("message", ""),
        "scheduled_at": time.time(),
        "fire_at": time.time() + delay,
    }
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    pending_path(session_id).write_text(json.dumps(record))
    log(f"scheduled {kind} for {session_id} (+{delay}s)")
    spawn_worker(session_id)


def run_worker(session_id: str) -> None:
    cfg = load_config()
    delay = int(cfg.get("delay_seconds", 60))
    time.sleep(delay)

    p = pending_path(session_id)
    if not p.exists():
        log(f"worker: pending gone for {session_id}, exiting")
        return
    try:
        record = json.loads(p.read_text())
    except Exception as e:
        log(f"worker: bad pending file {p}: {e}")
        p.unlink(missing_ok=True)
        return

    if MUTE_SENTINEL.exists():
        MUTE_SENTINEL.unlink(missing_ok=True)
        p.unlink(missing_ok=True)
        log(f"worker: muted {session_id}")
        return

    # Build and send
    try:
        from send_discord import send  # local import
    except Exception as e:
        log(f"worker: import send_discord failed: {e}")
        p.unlink(missing_ok=True)
        return

    cwd = record.get("cwd") or "(unknown)"
    kind = record.get("kind")
    sid_short = (record.get("session_id") or "")[:8]

    if kind == "done":
        title = "✅ Claude finished"
        color = 0x57F287  # green
        last_msg = read_last_assistant_text(record.get("transcript_path"))
        body = last_msg or "(task complete — no final message captured)"
        fields = [
            {"name": "cwd", "value": f"`{cwd}`", "inline": False},
            {"name": "session", "value": sid_short or "—", "inline": True},
        ]
    else:  # await
        title = "⏸ Claude needs you"
        color = 0xFEE75C  # yellow
        reason = record.get("message") or "Claude is waiting for your input."
        body = reason
        fields = [
            {"name": "cwd", "value": f"`{cwd}`", "inline": False},
            {"name": "session", "value": sid_short or "—", "inline": True},
        ]

    try:
        send(title, body, color=color, fields=fields)
        log(f"worker: sent {kind} for {session_id}")
    except Exception as e:
        log(f"worker: send failed for {session_id}: {e}")
    finally:
        p.unlink(missing_ok=True)


def cli_enable(cwd: str) -> None:
    p = cwd_marker_path(cwd)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(os.path.abspath(cwd))
    print(f"Discord notifications ON for {os.path.abspath(cwd)}")


def cli_disable(cwd: str) -> None:
    p = cwd_marker_path(cwd)
    existed = p.exists()
    p.unlink(missing_ok=True)
    # Drop any pending notification for this cwd too, so nothing fires after disable.
    if PENDING_DIR.exists():
        abs_cwd = os.path.abspath(cwd)
        for pf in PENDING_DIR.iterdir():
            try:
                rec = json.loads(pf.read_text())
                if os.path.abspath(rec.get("cwd") or "") == abs_cwd:
                    pf.unlink(missing_ok=True)
            except Exception:
                pass
    suffix = "" if existed else " (was already off)"
    print(f"Discord notifications OFF for {os.path.abspath(cwd)}{suffix}")


def cli_status(cwd: str) -> None:
    state = "ON" if is_enabled(cwd) else "OFF"
    print(f"Discord notifications: {state} for {os.path.abspath(cwd)}")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        run_worker(sys.argv[2])
        return
    if len(sys.argv) >= 2 and sys.argv[1] in ("--enable", "--disable", "--status"):
        cwd = os.getcwd()
        {"--enable": cli_enable, "--disable": cli_disable, "--status": cli_status}[sys.argv[1]](cwd)
        return
    try:
        handle_hook()
    except Exception as e:
        log(f"hook error: {e}")


if __name__ == "__main__":
    main()
