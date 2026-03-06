# Claude Session Manager

Claude Code skills for managing sessions — list all sessions with metadata and clean up unused ones.

## Skills

### sessions-list

List all Claude Code sessions with name, ID, project, last active time, size, and message count.

```
/sessions-list
/sessions-list --project <substring>
```

### sessions-clean

Clean up Claude Code sessions. Supports two modes:

- **`empty`** (default) — removes unnamed sessions ≤ 4KB (empty/tiny sessions)
- **`unnamed`** — removes all unnamed sessions regardless of size

Always confirms before deleting.

```
/sessions-clean              # default: empty mode
/sessions-clean empty        # same as above
/sessions-clean unnamed      # all unnamed sessions
/sessions-clean <SESSION_ID> # target a specific session by ID prefix
```

## Installation

Copy the skill directories to `~/.claude/skills/`:

```bash
cp -r sessions-list sessions-clean ~/.claude/skills/
```

## Requirements

- Python 3.13+
- Claude Code CLI
