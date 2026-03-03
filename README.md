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

Clean up Claude Code sessions. Without arguments, lists all unnamed sessions for bulk cleanup. With a `SESSION_ID` argument, targets that specific session. Always confirms before deleting.

```
/sessions-clean
/sessions-clean <SESSION_ID>
```

## Installation

Copy the skill directories to `~/.claude/skills/`:

```bash
cp -r sessions-list sessions-clean ~/.claude/skills/
```

## Requirements

- Python 3.13+
- Claude Code CLI
