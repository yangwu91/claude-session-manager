---
name: sessions-clean
description: "Clean up Claude Code sessions. Supports: `empty` (default) removes unnamed sessions \u2264 10KB, `unnamed` removes all unnamed sessions, or one or more session IDs/names to delete specific sessions. Partial ID prefixes and name matching supported. Always confirms before deleting."
---

# Clean Sessions

## Instructions

### Step 1: Run the detection script

Parse the user's arguments and run:

```bash
/usr/local/bin/python3.13 ~/.claude/skills/sessions-clean/scripts/clean_sessions.py [ARGS...]
```

- No argument or `empty` → unnamed sessions ≤ 10KB
- `unnamed` → all unnamed sessions regardless of size
- One or more **session IDs or names** → targeted deletion (space-separated)
  - Supports partial ID prefixes (e.g., `0fa7` matches `0fa78bf1-...`)
  - Supports name matching: exact match first, then substring (case-insensitive)

### Step 2: Handle target resolution

The script returns a `target_results` array (in targeted mode) showing what each query matched.

For each target in `target_results`:

- **`no_match`**: Report that no session matched this query.
- **`match_count == 1`**: Resolved — include in deletion list.
- **`match_count > 1`**: Ambiguous — present the matching sessions and use `AskUserQuestion` (with `multiSelect: true`) to let the user pick which ones to delete. Then add selected sessions to the deletion list.

### Step 3: Present the resolved sessions

Show a summary table of all sessions to be deleted:

| # | Name | ID | Last Active | Size |
|---|------|----|-------------|------|

- Show session ID as first 8 characters in backticks
- Show `last_ts` formatted as `YYYY-MM-DD HH:MM`, or `?` if null
- Prefix named sessions with `*`

**IMPORTANT:** If the final list is empty (all queries had no matches), tell the user and stop.

### Step 4: Confirm with the user

Use `AskUserQuestion` to ask for confirmation:

- Option 1: "Delete" (with count and total size)
- Option 2: "Cancel"

**CRITICAL:** Never delete without user confirmation.

### Step 5: Execute deletion

If the user confirms, delete the files listed in each session's `paths_to_delete` array:

```bash
rm -f <jsonl_file>
rm -rf <session_subdirectory>
```

Execute one `rm` command per session.

### Step 6: Report results

After deletion, report:
- Number of sessions deleted
- Total space freed
