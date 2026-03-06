---
name: sessions-list
description: List all Claude Code sessions with name, ID, project, last active time, size, and message count. Use when the user wants to see, list, or browse their sessions.
---

# List Sessions

## Instructions

### Step 1: Run the detection script

```bash
/usr/local/bin/python3.13 ~/.claude/skills/sessions-list/scripts/list_sessions.py
```

If the user provides a `--project <substring>` argument, pass it through to filter by project path.

### Step 2: Present the results

Read the JSON output. Show the user a **Markdown table** with these columns:
`# | Name | ID | Project | Last Active | Size | Msgs`

- Each row corresponds to one session from the JSON output
- Keep the same sort order (most recent first, already sorted by script)
- For named sessions (`is_named: true`), prefix the name with `*`
- For current project sessions (`is_current_project: true`), prefix the project with `>`
- For the current session (`is_current_session: true`), append `(current)` after the name
- Show session ID as first 8 characters in backticks
- Show `last_ts` formatted as `YYYY-MM-DD HH:MM`, or `?` if null

Example format:

| # | Name | ID | Project | Last Active | Size | Msgs |
|---|------|----|---------|-------------|------|------|
| 1 | current-task (current) | `abc12345` | >my-project | 2026-03-02 09:00 | 173 KB | 38 |
| 2 | *my-session | `def45678` | other-project | 2026-03-01 15:00 | 2.6 MB | 114 |

After the table, show the summary line:
**Total: {total_size_human}** across {count} sessions ({named_count} named, {unnamed_count} unnamed).

### Step 3: Offer follow-up actions

If the user asks about a specific session, you can offer to:
- Show more details (read the JSONL file)
- Clean it up (suggest using `/sessions-clean`)
- Resume it (use `/resume SESSION_ID`)
