---
name: sessions
description: "List and clean Claude Code sessions. Subcommands: `list` (default) shows sessions with optional filtering; `clean` deletes sessions. Filters (AND-combined, any order): `unnamed`, `size>10MB`, `age>30d`, etc. Clean also supports empty mode and targeted IDs/names."
---

# Sessions

Manage Claude Code sessions: list or clean.

## Dispatch

Look at the user's first argument:

- First arg is `clean` → run **clean** subcommand with the remaining args
- First arg is `list` → run **list** subcommand with the remaining args
- No args, or first arg is a filter (`unnamed`, `size...`, `age...`), or a `--project ...` flag → run **list** subcommand with all args

Never treat the first arg as a session target unless the subcommand is explicitly `clean`.

## Filter syntax (shared by list and clean)

All filters AND together. Order does not matter.

| Filter | Meaning |
|---|---|
| `unnamed` | Sessions without a custom name |
| `size>10MB` / `size<100KB` / `size>=1G` / `size<=50k` | Size comparison. Unit suffix optional: B/K/M/G, KB/MB/GB (case-insensitive). No suffix = bytes. |
| `age>30d` / `age<7d` / `age>=1w` / `age<=1m` | Time since last activity. Units: `h` hour / `d` day / `w` week / `m` month (30 days). |

Malformed filters (e.g. `size>10xyz`), unknown units, or impossible ranges (e.g. `size>10MB size<1MB`) produce an error — the script exits non-zero with a JSON error message. Relay the error to the user verbatim and stop.

---

## list subcommand

### Invoke

```bash
/usr/local/bin/python3.13 ~/.claude/skills/sessions/scripts/sessions.py list [FILTERS...] [--project SUBSTR]
```

`--project SUBSTR` restricts to sessions whose cwd contains the substring.

### Present the output

Read the JSON. If it contains an `error` field, report it and stop. Otherwise show a Markdown table:

| # | Name | ID | Project | Last Active | Size | Msgs |

Conventions:
- Rows are already sorted (most recent first) — preserve that order
- Named sessions (`is_named: true`): prefix name with `*`
- Current project (`is_current_project: true`): prefix project with `>`
- Current session (`is_current_session: true`): append `(current)` after the name
- Show session ID as first 8 characters in backticks
- Format `last_ts` as `YYYY-MM-DD HH:MM`, or `?` if null

After the table, show:
**Total: {total_size_human}** across {count} sessions ({named_count} named, {unnamed_count} unnamed).

If filters were applied, prepend a line: `Filters: {filters_applied joined with " AND "}`.

### Follow-up

If the user asks about a specific session, offer:
- Show more detail (read the JSONL file)
- Clean it up (suggest `/sessions clean <id>`)
- Resume it (use `/resume SESSION_ID`)

---

## clean subcommand

### Invoke

```bash
/usr/local/bin/python3.13 ~/.claude/skills/sessions/scripts/sessions.py clean [ARGS...]
```

The script auto-detects one of three modes from the args. Modes cannot be mixed — mixing raises an error.

### The three modes

1. **empty** — no args, or just `empty`. Deletes unnamed sessions ≤ 10KB (safe default for trashing aborted starts).
   ```
   /sessions clean
   /sessions clean empty
   ```

2. **targeted** — one or more session IDs (full or prefix) or names (exact or substring, case-insensitive), space-separated. Multiple targets OR together.
   ```
   /sessions clean 0fa7
   /sessions clean my-debug abc12345 another-name
   ```

3. **filter** — any combination of `unnamed`, `size{op}N`, `age{op}N`. All AND'd.
   ```
   /sessions clean unnamed
   /sessions clean unnamed size>10MB age>30d
   /sessions clean size>1MB size<100MB
   ```

Trying to mix modes (e.g. `clean empty 0fa7` or `clean 0fa7 size>10MB`) is rejected with an error.

### Handle the JSON output

- **`error`** field present → relay to user and stop.
- **`mode == "targeted"`** → walk `target_results`:
  - `match_count == 0` (`no_match`) → tell the user this query matched nothing.
  - `match_count == 1` → include in deletion list.
  - `match_count > 1` → ambiguous. Show the matches and use `AskUserQuestion` with `multiSelect: true` to let the user pick which ones to delete. Add chosen ones to the deletion list.
- **`mode == "empty"` / `"filter"`** → `sessions` is the full deletion list.

### Present the deletion list

Show a Markdown table of the sessions to delete:

| # | Name | ID | Last Active | Size |

- Show ID as first 8 chars in backticks
- Format `last_ts` as `YYYY-MM-DD HH:MM`, or `?` if null
- Prefix named sessions with `*`

**If the final list is empty** (all queries returned no matches, or filters matched nothing): tell the user, then stop. Do not proceed to confirmation.

### Confirm before deleting

Use `AskUserQuestion`:
- Option 1: `Delete` — include the count and total size (e.g. `"Delete 5 sessions (12.4 MB)"`)
- Option 2: `Cancel`

**CRITICAL: Never delete without explicit user confirmation.**

### Execute deletion

On confirm, run one command per session using its `paths_to_delete` array:

```bash
rm -f <paths_to_delete[0]>              # the .jsonl file
rm -rf <paths_to_delete[1]>             # the UUID subdirectory (if present)
```

### Report results

After deletion:
- Number of sessions deleted
- Total space freed (sum of their `total_size`)
