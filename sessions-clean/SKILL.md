---
name: sessions-clean
description: Clean up Claude Code sessions. Without arguments, lists all unnamed sessions for bulk cleanup. With a SESSION_ID argument (full or prefix), targets that specific session. Always confirms before deleting.
---

# Clean Sessions

## Instructions

### Step 1: Run the detection script

Parse the user's argument (if any) and run:

```bash
/usr/local/bin/python3.13 ~/.claude/skills/sessions-clean/scripts/clean_sessions.py [SESSION_ID]
```

- No argument → script returns all **unnamed** sessions (candidates for cleanup)
- `SESSION_ID` argument → script returns matching session(s) by ID prefix

### Step 2: Present the results

Read the JSON output. Show the user a summary:

- How many sessions will be deleted
- Total size to be freed
- List each session: name/slug, session ID (first 8 chars), last active date, size

**IMPORTANT:** If `count` is 0, tell the user there's nothing to clean and stop.

### Step 3: Confirm with the user

Use `AskUserQuestion` to ask for confirmation before deleting:

- Option 1: "Delete all listed sessions" (with count and size)
- Option 2: "Cancel"

**CRITICAL:** Never delete without user confirmation.

### Step 4: Execute deletion

If the user confirms, delete the files listed in each session's `paths_to_delete` array:

```bash
rm -f <jsonl_file>
rm -rf <session_subdirectory>
```

Execute one `rm` command per session. Report progress as you go.

### Step 5: Report results

After deletion, report:
- Number of sessions deleted
- Total space freed
