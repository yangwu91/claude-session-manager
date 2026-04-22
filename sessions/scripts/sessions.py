#!/usr/bin/env python3
"""Sessions management: list and clean Claude Code sessions.

Usage:
  sessions.py list  [FILTERS...] [--project SUBSTR]
  sessions.py clean [FILTERS... | TARGETS... | empty]

Filters (AND-combined, positions interchangeable):
  unnamed              sessions without a custom name
  size{>,<,>=,<=}N[U]  U in B/K/M/G (or KB/MB/GB); default B
  age{>,<,>=,<=}N{h|d|w|m}  hours/days/weeks/months (m = 30 days)
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone


# ========== shared helpers ==========

def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def dir_size(path: Path) -> int:
    total = 0
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return total


def extract_first_user_text(content) -> str | None:
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        text = " ".join(texts).strip()
    else:
        return None

    if not text:
        return None

    skip_prefixes = (
        "<local-command", "[Request interrupted", "<system-reminder",
        "<command-name", "<command-message",
        "Implement the following plan:",
        "Base directory for this skill:",
        "Unknown skill:",
    )
    if any(text.startswith(p) for p in skip_prefixes):
        return None

    return " ".join(text.split())


# ========== filter parsing ==========

SIZE_UNITS = {
    "": 1, "b": 1,
    "k": 1024, "kb": 1024,
    "m": 1024 ** 2, "mb": 1024 ** 2,
    "g": 1024 ** 3, "gb": 1024 ** 3,
}

AGE_UNITS = {
    "h": 3600,
    "d": 86400,
    "w": 86400 * 7,
    "m": 86400 * 30,
}

SIZE_RE = re.compile(r"^size\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]{0,2})$")
AGE_RE = re.compile(r"^age\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z])$")


class Filter:
    __slots__ = ("kind", "op", "threshold", "raw")

    def __init__(self, kind: str, op: str | None, threshold: float | None, raw: str):
        self.kind = kind
        self.op = op
        self.threshold = threshold
        self.raw = raw

    def matches(self, session: dict) -> bool:
        if self.kind == "unnamed":
            return not session["is_named"]
        if self.kind == "size":
            return _cmp(session["total_size"], self.op, self.threshold)
        if self.kind == "age":
            if not session["last_ts"]:
                return False
            last = datetime.fromisoformat(session["last_ts"])
            age_sec = (datetime.now(timezone.utc) - last).total_seconds()
            return _cmp(age_sec, self.op, self.threshold)
        return False


def _cmp(a: float, op: str, b: float) -> bool:
    if op == ">":  return a > b
    if op == "<":  return a < b
    if op == ">=": return a >= b
    if op == "<=": return a <= b
    raise ValueError(f"unknown op: {op}")


def parse_filter_token(token: str) -> Filter | None:
    """Return a Filter if token is a filter expression, None if it looks like a target (ID/name).
    Raises ValueError on malformed filter syntax."""
    if token == "unnamed":
        return Filter("unnamed", None, None, token)

    low = token.lower()

    if low.startswith("size"):
        m = SIZE_RE.match(token)
        if not m:
            raise ValueError(
                f"malformed size filter '{token}'. "
                f"expected e.g. 'size>10MB', 'size<=100K', 'size>1G'."
            )
        op, val, unit = m.groups()
        unit = unit.lower()
        if unit not in SIZE_UNITS:
            raise ValueError(
                f"invalid size unit '{unit}' in '{token}'. "
                f"use one of: B/K/KB/M/MB/G/GB."
            )
        threshold = float(val) * SIZE_UNITS[unit]
        return Filter("size", op, threshold, token)

    if low.startswith("age"):
        m = AGE_RE.match(token)
        if not m:
            raise ValueError(
                f"malformed age filter '{token}'. "
                f"expected e.g. 'age>30d', 'age<7d', 'age>=1w'."
            )
        op, val, unit = m.groups()
        unit = unit.lower()
        if unit not in AGE_UNITS:
            raise ValueError(
                f"invalid age unit '{unit}' in '{token}'. "
                f"use one of: h/d/w/m (hour/day/week/month)."
            )
        threshold = float(val) * AGE_UNITS[unit]
        return Filter("age", op, threshold, token)

    return None


def detect_conflicts(filters: list[Filter]) -> list[str]:
    """Return human-readable conflict messages for impossible filter ranges."""
    conflicts = []
    for kind in ("size", "age"):
        lower_val: float | None = None
        lower_strict = False
        lower_tokens: list[str] = []
        upper_val: float | None = None
        upper_strict = False
        upper_tokens: list[str] = []

        for f in filters:
            if f.kind != kind:
                continue
            strict = f.op in (">", "<")
            if f.op in (">", ">="):
                if lower_val is None or f.threshold > lower_val:
                    lower_val, lower_strict = f.threshold, strict
                    lower_tokens = [f.raw]
                elif f.threshold == lower_val:
                    lower_strict = lower_strict or strict
                    lower_tokens.append(f.raw)
            elif f.op in ("<", "<="):
                if upper_val is None or f.threshold < upper_val:
                    upper_val, upper_strict = f.threshold, strict
                    upper_tokens = [f.raw]
                elif f.threshold == upper_val:
                    upper_strict = upper_strict or strict
                    upper_tokens.append(f.raw)

        if lower_val is not None and upper_val is not None:
            impossible = (
                lower_val > upper_val
                or (lower_val == upper_val and (lower_strict or upper_strict))
            )
            if impossible:
                conflicts.append(
                    f"impossible {kind} range: {' AND '.join(lower_tokens + upper_tokens)}"
                )
    return conflicts


# ========== session parsing ==========

def parse_session(jsonl_path: Path) -> dict | None:
    session_id = jsonl_path.stem
    project_dir = jsonl_path.parent

    main_size = jsonl_path.stat().st_size
    sub_dir = project_dir / session_id
    sub_size = dir_size(sub_dir) if sub_dir.is_dir() else 0
    total_size = main_size + sub_size

    cwd = None
    custom_name = None
    last_ts: datetime | None = None
    last_user_msg = None
    message_count = 0

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_str = entry.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except (ValueError, TypeError):
                        pass

                if cwd is None and entry.get("cwd"):
                    cwd = entry["cwd"]

                rename_text = None
                if entry.get("type") == "system" and entry.get("subtype") == "local_command":
                    rename_text = entry.get("content", "")
                elif entry.get("type") == "user":
                    msg = entry.get("message", {})
                    c = msg.get("content", "") if isinstance(msg.get("content"), str) else ""
                    if c.startswith("<local-command-stdout>Session renamed to:"):
                        rename_text = c

                if rename_text and "<local-command-stdout>Session renamed to:" in rename_text:
                    idx = rename_text.index("Session renamed to:") + len("Session renamed to:")
                    name_part = rename_text[idx:]
                    end_tag = name_part.find("</local-command-stdout>")
                    if end_tag != -1:
                        name_part = name_part[:end_tag]
                    custom_name = name_part.strip()

                if entry.get("type") == "user":
                    msg = entry.get("message", {})
                    text = extract_first_user_text(msg.get("content", ""))
                    if text:
                        last_user_msg = text

                if entry.get("type") in ("user", "assistant"):
                    message_count += 1

    except Exception:
        return None

    if cwd:
        home = str(Path.home())
        display_path = cwd.replace(home, "~")
        for prefix in ("~/Library/CloudStorage/SynologyDrive-WuNAS/", "~/SynologyDrive/WuNAS/"):
            if display_path.startswith(prefix):
                display_path = display_path[len(prefix):]
                break
        else:
            if display_path.startswith("~/"):
                display_path = display_path[2:]
        parts = [p for p in display_path.split("/") if p]
        if len(parts) > 3:
            short_project = "/".join(parts[-3:])
        elif parts:
            short_project = "/".join(parts)
        else:
            short_project = display_path
    else:
        short_project = project_dir.name

    if custom_name:
        display_name = custom_name
    elif last_user_msg:
        display_name = last_user_msg[:60] + "…" if len(last_user_msg) > 60 else last_user_msg
    else:
        display_name = "-"

    paths_to_delete = [str(jsonl_path)]
    if sub_dir.is_dir():
        paths_to_delete.append(str(sub_dir))

    return {
        "session_id": session_id,
        "name": display_name,
        "is_named": custom_name is not None,
        "project": short_project,
        "cwd": cwd or "(unknown)",
        "is_current_project": False,
        "is_current_session": False,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "message_count": message_count,
        "paths_to_delete": paths_to_delete,
    }


def collect_all_sessions(projects_dir: Path, project_filter: str | None = None) -> list[dict]:
    sessions = []
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_filter and project_filter not in str(project_dir):
            continue
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            if jsonl_file.parent != project_dir:
                continue
            info = parse_session(jsonl_file)
            if info:
                sessions.append(info)
    return sessions


def mark_current(sessions: list[dict], projects_dir: Path) -> str | None:
    """Mark is_current_project and is_current_session based on cwd + mtime. Returns current session_id."""
    try:
        current_cwd = str(Path(os.getcwd()).resolve())
    except Exception:
        return None
    if not current_cwd:
        return None

    best_mtime = 0.0
    current_session_id = None
    for s in sessions:
        session_cwd = s.get("cwd", "")
        try:
            resolved = str(Path(session_cwd).resolve()) if session_cwd else ""
        except Exception:
            resolved = session_cwd
        if resolved == current_cwd:
            s["is_current_project"] = True
            for project_dir in sorted(projects_dir.iterdir()):
                candidate = project_dir / f"{s['session_id']}.jsonl"
                if candidate.exists():
                    mtime = candidate.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        current_session_id = s["session_id"]
                    break

    if current_session_id:
        for s in sessions:
            if s["session_id"] == current_session_id:
                s["is_current_session"] = True
                break

    return current_session_id


# ========== subcommand: list ==========

def cmd_list(args: list[str]) -> None:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        print(json.dumps({"error": "no projects directory found", "count": 0, "sessions": []}))
        sys.exit(0)

    # Extract --project flag
    project_filter = None
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--project" and i + 1 < len(args):
            project_filter = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1

    # Parse filters
    filters: list[Filter] = []
    try:
        for tok in positional:
            f = parse_filter_token(tok)
            if f is None:
                print(json.dumps({
                    "error": f"'{tok}' is not a valid list filter. "
                             f"use: unnamed, size{{op}}N, age{{op}}N, or --project SUBSTR."
                }))
                sys.exit(2)
            filters.append(f)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)

    conflicts = detect_conflicts(filters)
    if conflicts:
        print(json.dumps({"error": "; ".join(conflicts)}))
        sys.exit(2)

    sessions = collect_all_sessions(projects_dir, project_filter)
    mark_current(sessions, projects_dir)

    # Apply filters (AND)
    if filters:
        sessions = [s for s in sessions if all(f.matches(s) for f in filters)]

    sessions.sort(key=lambda s: s["last_ts"] or "", reverse=True)

    total_size = sum(s["total_size"] for s in sessions)
    named_count = sum(1 for s in sessions if s["is_named"])

    result = {
        "count": len(sessions),
        "named_count": named_count,
        "unnamed_count": len(sessions) - named_count,
        "project_count": len(set(s["project"] for s in sessions)),
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "filters_applied": [f.raw for f in filters],
        "project_filter": project_filter,
        "sessions": [
            {k: v for k, v in s.items() if k != "paths_to_delete"}
            for s in sessions
        ],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ========== subcommand: clean ==========

def find_matches(target: str, all_sessions: list[dict]) -> tuple[str, list[dict]]:
    matched = [s for s in all_sessions if s["session_id"].startswith(target)]
    if matched:
        return ("id_prefix", matched)
    matched = [s for s in all_sessions if s["name"].lower() == target.lower()]
    if matched:
        return ("name_exact", matched)
    matched = [s for s in all_sessions if target.lower() in s["name"].lower()]
    if matched:
        return ("name_substring", matched)
    return ("no_match", [])


def classify_clean_args(args: list[str]) -> tuple[str, list[Filter], list[str]]:
    """Determine clean mode and validate no mixing. Returns (mode, filters, targets)."""
    if not args:
        return ("empty", [], [])

    has_empty = False
    filters: list[Filter] = []
    targets: list[str] = []

    for arg in args:
        if arg == "empty":
            has_empty = True
            continue
        f = parse_filter_token(arg)  # raises ValueError on malformed filter
        if f is not None:
            filters.append(f)
        else:
            targets.append(arg)

    modes = []
    if has_empty:
        modes.append("empty")
    if filters:
        modes.append("filter")
    if targets:
        modes.append("targeted")

    if len(modes) > 1:
        raise ValueError(
            f"cannot mix modes: {' + '.join(modes)}. "
            f"use only one of: `empty` alone, targets (IDs/names), "
            f"or filters (unnamed / size / age)."
        )

    if "empty" in modes:
        return ("empty", [], [])
    if "filter" in modes:
        return ("filter", filters, [])
    return ("targeted", [], targets)


def cmd_clean(args: list[str]) -> None:
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        print(json.dumps({"error": "no projects directory found", "sessions": []}))
        sys.exit(0)

    try:
        mode, filters, targets = classify_clean_args(args)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)

    if filters:
        conflicts = detect_conflicts(filters)
        if conflicts:
            print(json.dumps({"error": "; ".join(conflicts)}))
            sys.exit(2)

    all_sessions = collect_all_sessions(projects_dir)
    current_session_id = mark_current(all_sessions, projects_dir)

    # Exclude the current session from deletion candidates
    candidate_sessions = [s for s in all_sessions if s["session_id"] != current_session_id]

    if mode == "empty":
        sessions = [s for s in candidate_sessions if not s["is_named"] and s["total_size"] <= 10240]
        sessions.sort(key=lambda s: s["last_ts"] or "")
        total = sum(s["total_size"] for s in sessions)
        print(json.dumps({
            "mode": "empty",
            "count": len(sessions),
            "total_size": total,
            "total_size_human": human_size(total),
            "sessions": sessions,
        }, indent=2, ensure_ascii=False))
        return

    if mode == "filter":
        sessions = [s for s in candidate_sessions if all(f.matches(s) for f in filters)]
        sessions.sort(key=lambda s: s["last_ts"] or "")
        total = sum(s["total_size"] for s in sessions)
        print(json.dumps({
            "mode": "filter",
            "filters_applied": [f.raw for f in filters],
            "count": len(sessions),
            "total_size": total,
            "total_size_human": human_size(total),
            "sessions": sessions,
        }, indent=2, ensure_ascii=False))
        return

    # targeted mode
    target_results = []
    seen_ids: set[str] = set()
    resolved_sessions: list[dict] = []

    for target in targets:
        match_type, matched = find_matches(target, candidate_sessions)
        target_results.append({
            "query": target,
            "match_type": match_type,
            "match_count": len(matched),
            "sessions": [
                {
                    "session_id": s["session_id"],
                    "name": s["name"],
                    "is_named": s["is_named"],
                    "last_ts": s["last_ts"],
                    "total_size": s["total_size"],
                    "total_size_human": s["total_size_human"],
                }
                for s in matched
            ],
        })
        for s in matched:
            if s["session_id"] not in seen_ids:
                seen_ids.add(s["session_id"])
                resolved_sessions.append(s)

    resolved_sessions.sort(key=lambda s: s["last_ts"] or "")
    total = sum(s["total_size"] for s in resolved_sessions)
    print(json.dumps({
        "mode": "targeted",
        "target_results": target_results,
        "count": len(resolved_sessions),
        "total_size": total,
        "total_size_human": human_size(total),
        "sessions": resolved_sessions,
    }, indent=2, ensure_ascii=False))


# ========== entry ==========

def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: sessions.py {list|clean} [args...]"}))
        sys.exit(2)

    sub = sys.argv[1]
    rest = sys.argv[2:]

    if sub == "list":
        cmd_list(rest)
    elif sub == "clean":
        cmd_clean(rest)
    else:
        print(json.dumps({"error": f"unknown subcommand: {sub}. use 'list' or 'clean'."}))
        sys.exit(2)


if __name__ == "__main__":
    main()
