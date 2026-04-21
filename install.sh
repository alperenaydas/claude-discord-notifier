#!/usr/bin/env bash
# Installer for claude-discord-notifier.
# Idempotent: safe to re-run. Preserves any existing Claude Code hooks.
#
# Non-interactive usage (for scripted installs):
#   DISCORD_BOT_TOKEN=... DISCORD_USER_ID=... ./install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD_DIR="$SCRIPT_DIR/payload"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
NOTIFIER_DIR="$CLAUDE_DIR/notifier"
COMMANDS_DIR="$CLAUDE_DIR/commands"
SETTINGS="$CLAUDE_DIR/settings.json"
CONFIG="$NOTIFIER_DIR/config.json"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 is required but not found on PATH."

[[ -d "$PAYLOAD_DIR" ]] || die "Payload directory not found at $PAYLOAD_DIR"

say "Creating directories under $CLAUDE_DIR"
mkdir -p "$NOTIFIER_DIR/state/pending" \
         "$NOTIFIER_DIR/state/enabled" \
         "$NOTIFIER_DIR/logs" \
         "$COMMANDS_DIR"

say "Copying notifier scripts"
cp "$PAYLOAD_DIR/notifier.py"     "$NOTIFIER_DIR/notifier.py"
cp "$PAYLOAD_DIR/send_discord.py" "$NOTIFIER_DIR/send_discord.py"

say "Copying slash commands (discord-*.md)"
cp "$PAYLOAD_DIR"/commands/discord-*.md "$COMMANDS_DIR/"

# --- config.json: create only if missing; otherwise keep existing ---
if [[ -f "$CONFIG" ]]; then
    say "Keeping existing config at $CONFIG"
else
    BOT_TOKEN="${DISCORD_BOT_TOKEN:-}"
    USER_ID="${DISCORD_USER_ID:-}"
    if [[ -z "$BOT_TOKEN" ]]; then
        printf '\nPaste your Discord bot token (from Developer Portal → Bot → Reset Token): '
        read -rs BOT_TOKEN; echo
    fi
    if [[ -z "$USER_ID" ]]; then
        printf 'Paste your Discord user ID (enable Developer Mode, right-click your name → Copy User ID): '
        read -r USER_ID
    fi
    [[ -n "$BOT_TOKEN" && -n "$USER_ID" ]] || die "bot_token and user_id are required."

    say "Writing $CONFIG"
    CFG_PATH="$CONFIG" BOT_TOKEN="$BOT_TOKEN" USER_ID="$USER_ID" python3 - <<'PY'
import json, os, pathlib
pathlib.Path(os.environ["CFG_PATH"]).write_text(json.dumps({
    "bot_token": os.environ["BOT_TOKEN"],
    "user_id": os.environ["USER_ID"],
    "delay_seconds": 60,
    "stale_after_seconds": 600,
}, indent=2) + "\n")
PY
    chmod 600 "$CONFIG"
fi

# --- settings.json: merge hook entries idempotently ---
say "Wiring hooks into $SETTINGS (backup at ${SETTINGS}.bak)"
[[ -f "$SETTINGS" ]] && cp "$SETTINGS" "${SETTINGS}.bak"

SETTINGS_PATH="$SETTINGS" NOTIFIER_PY="$NOTIFIER_DIR/notifier.py" python3 - <<'PY'
import json, os, pathlib, sys

settings_path = pathlib.Path(os.environ["SETTINGS_PATH"])
notifier_py = os.environ["NOTIFIER_PY"]

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except Exception as e:
        print(f"settings.json is not valid JSON ({e}); aborting so nothing is lost.", file=sys.stderr)
        sys.exit(1)
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

EVENTS = ["Stop", "Notification", "UserPromptSubmit", "PreToolUse", "PostToolUse"]

def already_wired(event_arr, needle):
    for entry in event_arr:
        for h in entry.get("hooks", []) or []:
            if needle in (h.get("command") or ""):
                return True
    return False

added = []
for event in EVENTS:
    arr = hooks.setdefault(event, [])
    if already_wired(arr, notifier_py):
        continue
    arr.append({
        "hooks": [{
            "type": "command",
            "command": f"cat | CLAUDE_NOTIFIER_EVENT={event} python3 {notifier_py}",
            "async": True,
        }]
    })
    added.append(event)

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"hooks added for: {', '.join(added) if added else '(none — already wired)'}")
PY

# --- Test ---
say "Sending a test DM to verify setup"
if python3 "$NOTIFIER_DIR/send_discord.py" "install.sh test from $(hostname)"; then
    say "Success. Check Discord for the test DM."
else
    warn "Test send failed. Check $NOTIFIER_DIR/config.json and that the bot shares a server with you."
fi

cat <<EOF

Installed. Usage inside Claude Code:
  /discord-on       enable notifications for the current working directory
  /discord-off      disable them
  /discord-status   show current state
  /discord-mute     suppress the next single notification
  /discord-test     send a test DM

Config:  $CONFIG
Logs:    $NOTIFIER_DIR/logs/notifier.log
Uninstall: $SCRIPT_DIR/uninstall.sh
EOF
