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

Clean up Claude Code sessions. Supports batch mode and targeted deletion:

- **`empty`** (default) — removes unnamed sessions ≤ 10KB (empty/tiny sessions)
- **`unnamed`** — removes all unnamed sessions regardless of size
- **One or more session IDs or names** — delete specific sessions by ID prefix or name

Matching priority for targeted deletion:
1. **ID prefix** — e.g., `0fa7` matches `0fa78bf1-...`
2. **Exact name** (case-insensitive) — e.g., `my-project` matches a session named "my-project"
3. **Name substring** (case-insensitive) — e.g., `dev` matches "dev-frontend" and "dev-backend"

If a query matches multiple sessions, you'll be asked to pick which ones to delete. Always confirms before deleting.

```
/sessions-clean                        # default: empty mode
/sessions-clean empty                  # same as above
/sessions-clean unnamed                # all unnamed sessions
/sessions-clean my-project             # delete session named "my-project"
/sessions-clean 0fa7                   # delete session with ID starting with 0fa7
/sessions-clean my-project dev-task a3b # delete multiple sessions at once
```

## Installation

Copy the skill directories to `~/.claude/skills/`:

```bash
cp -r sessions-list sessions-clean ~/.claude/skills/
```

## Requirements

- Python 3.13+
- Claude Code CLI
