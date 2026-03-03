---
name: sessions-list
description: List all Claude Code sessions with name, ID, project, last active time, size, and message count. Use when the user wants to see, list, or browse their sessions.
---

# List Sessions

## Instructions

1. Run the detection script:

```bash
/usr/local/bin/python3.13 ~/.claude/skills/sessions-list/scripts/list_sessions.py
```

If the user provides a `--project <substring>` argument, pass it through to filter by project path.

2. Display the script output directly to the user — it produces a fixed-width table.

3. After displaying the script output, reformat the session list as a **Markdown table** with the same columns:
   `# | Name | ID | Project | Last Active | Size | Msgs`

   - Each row corresponds to one session from the script output
   - Keep the same sort order (most recent first)
   - Preserve `*` prefix for named sessions and `>` for current project

   Example format:

   | # | Name | ID | Project | Last Active | Size | Msgs |
   |---|------|-----|---------|-------------|------|------|
   | 1 | current-task... | abc123... | >my-project | 2026-03-02 09:00 | 173 KB | 38 |
   | 2 | *my-session | def456... | other-project | 2026-03-01 15:00 | 2.6 MB | 114 |

4. If the user asks about a specific session, you can offer to:
   - Show more details (read the JSONL file)
   - Clean it up (suggest using `/sessions-clean`)
   - Resume it (use `/resume SESSION_ID`)
