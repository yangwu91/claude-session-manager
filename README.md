# Claude Session Manager

**English** | [中文](./README_SC.md)

A Claude Code skill for managing your sessions: list them with rich metadata, clean them up with flexible filters. One skill, two subcommands — `list` and `clean`.

## Install

```bash
cp -r sessions ~/.claude/skills/
```

Then in Claude Code:

```
/sessions                    # list (default)
/sessions list               # list, explicit
/sessions clean              # clean (default: empty mode)
```

## Filter syntax (shared by `list` and `clean`)

All filters AND together. Order doesn't matter.

| Filter | Meaning |
|---|---|
| `unnamed` | Sessions without a custom name (never renamed via `/rename`). |
| `size>10MB` / `size<100KB` / `size>=1G` / `size<=50k` | Size comparison on total session size (jsonl + subdirectory). Unit suffix optional and case-insensitive: `B` / `K` / `KB` / `M` / `MB` / `G` / `GB`. No suffix = bytes. |
| `age>30d` / `age<7d` / `age>=1w` / `age<=1m` | Time since last activity. Units: `h` hour, `d` day, `w` week, `m` month (30 days). |

Error cases the script catches before touching anything:

- **Malformed filter** — e.g. `size>10xyz` → explains valid units
- **Impossible range** — e.g. `size>10MB size<1MB` → explains the contradiction
- **Mode mixing in `clean`** — e.g. `clean empty 0fa7` → explains the rule

## `/sessions list [filters...] [--project SUBSTR]`

Lists sessions with optional filtering.

```
/sessions                              # all sessions
/sessions unnamed                      # only unnamed
/sessions size>10M age>30d             # big and old
/sessions list size<100K               # small (the leading `list` is optional)
/sessions --project myapp              # cwd contains "myapp"
/sessions unnamed size>1M --project myapp
```

Output: a Markdown table with name, ID (first 8 chars), project, last-active timestamp, size, and message count. Conventions:

- Current project prefixed with `>`
- Current session appended with `(current)`
- Named sessions prefixed with `*`

Followed by a summary line: total size across N sessions (M named, K unnamed).

## `/sessions clean [args...]`

Deletes sessions. Three mutually-exclusive modes — the script auto-detects from args and rejects mixing.

### 1. Empty mode (default)

No args or just `empty`. Deletes unnamed sessions ≤ 10KB. The safe default for clearing aborted starts that never produced real content.

```
/sessions clean
/sessions clean empty
```

### 2. Targeted mode

One or more session IDs or names (space-separated). Multiple targets OR together.

Match priority per query:

1. **ID prefix** — e.g. `0fa7` matches `0fa78bf1-...`
2. **Exact name** (case-insensitive)
3. **Name substring** (case-insensitive)

If a query is ambiguous (matches multiple), Claude will ask you to pick which ones.

```
/sessions clean 0fa7
/sessions clean my-debug abc12345 another-name
```

### 3. Filter mode

Any combination of `unnamed`, `size{op}N`, `age{op}N`. All AND together.

```
/sessions clean unnamed
/sessions clean unnamed size>10MB age>30d
/sessions clean size>1MB size<100MB              # range query via two bounds
/sessions clean age>30d unnamed                  # order doesn't matter
```

## Safety

- Every delete asks for explicit confirmation via `AskUserQuestion` with the full list and total size.
- The **current session** is always excluded from deletion candidates (detected via `cwd` + last-activity timestamp).
- Ambiguous targets trigger a multi-select prompt.

## What gets deleted

For each session, exactly two paths:

- `~/.claude/projects/<project-dir>/<session-id>.jsonl` — the conversation log
- `~/.claude/projects/<project-dir>/<session-id>/` — the UUID subdirectory (planner state, todos, etc.), if it exists

**Not touched**:

- `~/.claude/projects/<project-dir>/memory/` — project-level memory (`MEMORY.md` and the `.md` files it references) survives untouched. Deleting a session does **not** lose memory.
- Other sessions in the same project — each session is an independent `<uuid>.jsonl` + `<uuid>/` pair.

## Requirements

- Python 3.13+
- Claude Code CLI

## License

MIT
