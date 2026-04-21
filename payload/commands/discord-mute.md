---
description: Suppress the next Discord notification from the notifier hook.
---

Run this exact bash command and nothing else, then reply in a single short line confirming the mute is armed:

```bash
touch ~/.claude/notifier/state/mute_next
```

The sentinel is consumed automatically when the next scheduled notification fires, so it only mutes one upcoming alert.
