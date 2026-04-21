#!/usr/bin/env bash
# Remove notifier hook entries from settings.json and delete notifier files.
# The Discord bot token lives in ~/.claude/notifier/config.json — deleted here.

set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
NOTIFIER_DIR="$CLAUDE_DIR/notifier"
COMMANDS_DIR="$CLAUDE_DIR/commands"
SETTINGS="$CLAUDE_DIR/settings.json"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

if [[ -f "$SETTINGS" ]]; then
    say "Removing notifier hook entries from $SETTINGS (backup at ${SETTINGS}.bak)"
    cp "$SETTINGS" "${SETTINGS}.bak"
    SETTINGS_PATH="$SETTINGS" python3 - <<'PY'
import json, os, pathlib
p = pathlib.Path(os.environ["SETTINGS_PATH"])
data = json.loads(p.read_text())
hooks = data.get("hooks", {})
for event, arr in list(hooks.items()):
    arr[:] = [e for e in arr if not any("/notifier/notifier.py" in (h.get("command") or "") for h in (e.get("hooks") or []))]
    if not arr:
        hooks.pop(event, None)
if not hooks:
    data.pop("hooks", None)
p.write_text(json.dumps(data, indent=2) + "\n")
PY
fi

say "Removing slash commands"
rm -f "$COMMANDS_DIR"/discord-on.md \
      "$COMMANDS_DIR"/discord-off.md \
      "$COMMANDS_DIR"/discord-status.md \
      "$COMMANDS_DIR"/discord-mute.md \
      "$COMMANDS_DIR"/discord-test.md

say "Removing $NOTIFIER_DIR"
rm -rf "$NOTIFIER_DIR"

say "Done."
