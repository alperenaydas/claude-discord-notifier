#!/usr/bin/env python3
"""Send a Discord DM to a specific user via bot token. Stdlib only.

Flow: open (or reuse) a DM channel with the user via POST /users/@me/channels,
then POST the message/embed to /channels/{channel_id}/messages.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
DM_CACHE = Path(__file__).parent / "state" / "dm_channel_id"
API = "https://discord.com/api/v10"


def load_config() -> dict:
    cfg = json.loads(CONFIG_PATH.read_text())
    token = (cfg.get("bot_token") or "").strip()
    uid = str(cfg.get("user_id") or "").strip()
    if not token or token.startswith("REPLACE_ME"):
        raise RuntimeError(f"bot_token not set in {CONFIG_PATH}")
    if not uid or uid.startswith("REPLACE_ME"):
        raise RuntimeError(f"user_id not set in {CONFIG_PATH}")
    return cfg


def _request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "ClaudeCodeNotifier (local, 1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"Discord {method} {path} -> {e.code}: {detail}") from None


def get_dm_channel_id(token: str, user_id: str) -> str:
    # Reuse cached channel id if we have one; Discord DM channel ids are stable per recipient.
    if DM_CACHE.exists():
        cid = DM_CACHE.read_text().strip()
        if cid.isdigit():
            return cid
    res = _request("POST", "/users/@me/channels", token, {"recipient_id": str(user_id)})
    cid = str(res.get("id") or "")
    if not cid:
        raise RuntimeError(f"no channel id in response: {res}")
    DM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DM_CACHE.write_text(cid)
    return cid


def send(title: str, body: str, color: int = 0x5865F2, fields: list[dict] | None = None) -> None:
    cfg = load_config()
    token = cfg["bot_token"].strip()
    user_id = str(cfg["user_id"]).strip()

    channel_id = get_dm_channel_id(token, user_id)
    payload = {
        "embeds": [
            {
                "title": title[:256],
                "description": body[:4000] if body else "",
                "color": color,
                "fields": fields or [],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            }
        ]
    }
    try:
        _request("POST", f"/channels/{channel_id}/messages", token, payload)
    except RuntimeError as e:
        # If the cached channel became invalid, drop cache and retry once.
        if "404" in str(e) or "Unknown Channel" in str(e):
            DM_CACHE.unlink(missing_ok=True)
            channel_id = get_dm_channel_id(token, user_id)
            _request("POST", f"/channels/{channel_id}/messages", token, payload)
        else:
            raise


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "test DM from send_discord.py"
    try:
        send("🔔 Test", msg, color=0x5865F2)
        print("sent")
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
