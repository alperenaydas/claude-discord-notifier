# claude-discord-notifier

Get a Discord DM on your phone when Claude Code finishes a task or halts waiting for your input — without giving Discord any control over the session. Claude still runs on your desktop; Discord is only a one-way alert channel.

Notifications are **opt-in per working directory**: run `/discord-on` in a session to enable, `/discord-off` to silence. A 60-second delay means no ping if you reply quickly.

## What each coworker needs

1. **Claude Code** installed and working.
2. **Python 3** on `PATH` (only stdlib is used — no `pip install` required).
3. A **Discord bot user** that shares at least one server with them.

## One-time Discord setup (per developer)

Each person creates their own bot so tokens aren't shared.

1. Go to https://discord.com/developers/applications → **New Application** → name it anything.
2. Left sidebar → **Bot** → (Add Bot if prompted) → **Reset Token** → copy it. You can only see it once.
3. Left sidebar → **OAuth2** → **URL Generator**:
   - scopes: `bot`
   - bot permissions: `Send Messages`
   - open the generated URL in your browser → add the bot to any server you're a member of. A brand-new 1-person server is fine; the bot just needs to share a guild with you. You never need to open that server again.
4. In Discord: *User Settings → Advanced → enable Developer Mode*. Right-click your own name → **Copy User ID**. This is a ~18-digit number.

## Install

```bash
git clone <this-repo>   # or: unzip the shared archive
cd claude-discord-notifier
./install.sh
```

The installer asks for your bot token and user ID (or accepts them via env vars — see below), copies the notifier under `~/.claude/notifier/`, installs the `/discord-*` slash commands, merges hook entries into `~/.claude/settings.json` (existing hooks preserved, `.bak` written), and sends a test DM.

**Non-interactive** (for dotfiles / provisioning scripts):

```bash
DISCORD_BOT_TOKEN=<token> DISCORD_USER_ID=<numeric-id> ./install.sh
```

The installer is **idempotent**: re-running it upgrades the scripts without duplicating hook entries or overwriting an existing `config.json`.

## Usage

Inside any Claude Code session:

| Command | Effect |
|---|---|
| `/discord-on` | enable notifications for the current cwd |
| `/discord-off` | disable them |
| `/discord-status` | show current state |
| `/discord-mute` | suppress the next single notification (one-shot) |
| `/discord-test` | send a test DM right now |

After `/discord-on`, whenever Claude finishes its turn *and you don't reply within 60 s*, your bot DMs you with:

- ✅ **Claude finished** — cwd + last assistant message
- ⏸ **Claude needs you** — cwd + reason (e.g. "Claude needs your permission to use Bash")

If you reply (or approve a tool) within the 60 s window, no notification is sent.

## Configuration

`~/.claude/notifier/config.json`:

```json
{
  "bot_token": "…",
  "user_id": "…",
  "delay_seconds": 60,
  "stale_after_seconds": 600
}
```

- `delay_seconds` — how long to wait after a Stop/Notification before DMing. Lower = more pings, less grace to reply.
- `stale_after_seconds` — pending notifications older than this are swept on the next hook invocation (covers crashes).

Logs: `~/.claude/notifier/logs/notifier.log` — each scheduled / cancelled / sent / muted event is recorded.

## Uninstall

```bash
./uninstall.sh
```

Removes the notifier directory, the slash commands, and strips notifier entries from `settings.json` (leaving unrelated hooks untouched; backup at `settings.json.bak`).

## How to share this with your team

Since everything sits in this one directory, any of these work:

- **Zip & send:** `cd .. && zip -r claude-discord-notifier.zip claude-discord-notifier && send via Slack/email`. Recipient: unzip, `cd`, `./install.sh`.
- **Internal git repo:** push this directory to your company GitLab/GitHub. Teammates `git clone` + `./install.sh`.
- **Public gist / repo:** same as above, using a public host.

No external dependencies, no build step, no package registry.

## Security notes

- The bot token is your Discord identity — never commit `config.json` or share it in chat.
- `config.json` is created with mode `600`.
- Each developer should create their own bot; do not share a single token across the team.
- The notifier only **sends** — it never reads DMs or accepts commands from Discord.
