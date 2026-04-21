# claude-discord-notifier

Get a Discord DM on your phone when [Claude Code](https://docs.claude.com/en/docs/claude-code) finishes a task or halts waiting for your input — without giving Discord any control over the session. Claude still runs on your desktop; Discord is only a one-way alert channel.

Notifications are **opt-in per working directory**: run `/discord-on` in a session to enable, `/discord-off` to silence. A 60-second delay before the DM is sent means no ping if you reply to Claude quickly.

## Why this exists

Most Claude × Telegram/Discord projects make the chat client a *remote control* for Claude — they stream the session to your phone and let you issue commands back. That's a lot of surface area and a lot of trust. This project does the opposite: it's a pure **warner**. Claude runs only where you started it; your phone just buzzes when it's idle or stuck.

## Requirements

- [Claude Code](https://docs.claude.com/en/docs/claude-code) installed and working.
- Python 3 on `PATH` (stdlib only — no `pip install` needed).
- A Discord bot user that shares at least one server with you.

## Set up a Discord bot (once)

1. Go to https://discord.com/developers/applications → **New Application** → name it anything (e.g. "Claude Notifier").
2. Left sidebar → **Bot** → (click **Add Bot** if prompted) → **Reset Token** → copy it. You can only see it once; store it somewhere safe.
3. Left sidebar → **OAuth2 → URL Generator**:
   - scopes: `bot`
   - bot permissions: `Send Messages`
   - open the generated URL → add the bot to a server you're a member of. A brand-new 1-person server is fine; the bot just needs to share a guild with you. You never need to open that server again.
4. In your Discord client: *User Settings → Advanced → enable Developer Mode*. Right-click your own name → **Copy User ID**. This is a ~18-digit number.

## Install

```bash
git clone https://github.com/<your-fork>/claude-discord-notifier.git
cd claude-discord-notifier
./install.sh
```

The installer will prompt for your bot token and user ID. It then copies the notifier under `~/.claude/notifier/`, installs the `/discord-*` slash commands, merges hook entries into `~/.claude/settings.json` (existing hooks preserved, backup written to `settings.json.bak`), and sends a test DM to confirm everything works.

**Non-interactive** (for dotfiles or provisioning scripts):

```bash
DISCORD_BOT_TOKEN=<token> DISCORD_USER_ID=<numeric-id> ./install.sh
```

The installer is **idempotent** — re-running it upgrades the scripts without duplicating hook entries or overwriting an existing `config.json`.

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

- ✅ **Claude finished** — cwd + the last assistant message
- ⏸ **Claude needs you** — cwd + reason (e.g. "Claude needs your permission to use Bash")

If you reply (or approve the tool) within the 60-second window, no notification is sent.

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

- `delay_seconds` — how long to wait after a Stop/Notification event before DMing. Lower = more pings, less grace to reply.
- `stale_after_seconds` — pending notifications older than this are swept on the next hook invocation (covers crashes and killed sessions).

Logs: `~/.claude/notifier/logs/notifier.log` — every scheduled / cancelled / sent / muted event is recorded.

## How it works

Claude Code exposes [hooks](https://docs.claude.com/en/docs/claude-code/hooks) — shell commands that fire on session events. The installer wires five events:

- **`Stop`** (task complete) and **`Notification`** (Claude is waiting on you) → schedule a notification.
- **`UserPromptSubmit`**, **`PreToolUse`**, **`PostToolUse`** (you're clearly active) → cancel any pending notification.

On a scheduling event, the hook writes a pending-notification file keyed by `session_id` and double-forks a detached Python worker. The worker sleeps `delay_seconds`, re-checks the pending file, and either sends the DM or exits silently (if you cancelled by acting, muted, or disabled for the cwd). The filesystem is the entire queue — no long-lived daemon to manage.

## Uninstall

```bash
./uninstall.sh
```

Removes the notifier directory, the slash commands, and strips notifier entries from `settings.json` (unrelated hooks are left untouched; backup at `settings.json.bak`).

## Security notes

- Your bot token is your Discord identity — never commit `config.json` or paste it in a chat/issue. The installer writes it with mode `600`.
- Create your own bot. Don't share a token across users.
- The notifier only **sends** DMs. It doesn't read messages, doesn't open a gateway connection, and can't be used to control your Claude session from Discord.

## Contributing

Issues and pull requests welcome. Some areas that would be nice to have:

- Per-cwd config overrides (e.g. a longer delay for long-running tasks).
- Support for other delivery channels (Telegram, ntfy, Slack) behind the same `send(...)` interface.
- Better extraction of the "reason" from `Notification` events across Claude Code versions.
- A matching installer for Windows / PowerShell.

If you're fixing a bug, please include the relevant log line from `~/.claude/notifier/logs/notifier.log` in the issue.

## License

MIT. See [`LICENSE`](LICENSE).
