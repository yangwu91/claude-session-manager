#!/usr/bin/env python3
"""List all Claude Code sessions with metadata."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone


def human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def dir_size(path: Path) -> int:
    """Calculate total size of a directory recursively."""
    total = 0
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return total


def display_width(text: str) -> int:
    """Calculate display width accounting for CJK double-width characters."""
    import unicodedata
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def truncate(text: str, max_width: int) -> str:
    """Truncate text to max display width, adding ellipsis if needed."""
    if display_width(text) <= max_width:
        return text
    result = []
    w = 0
    for ch in text:
        import unicodedata
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > max_width - 1:  # leave room for …
            break
        result.append(ch)
        w += cw
    return "".join(result) + "…"


def pad_to_width(text: str, width: int) -> str:
    """Pad text with spaces to reach target display width."""
    current = display_width(text)
    if current >= width:
        return text
    return text + " " * (width - current)


def extract_first_user_text(content) -> str | None:
    """Extract plain text from user message content (str or list)."""
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        # content is a list of content blocks
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        text = " ".join(texts).strip()
    else:
        return None

    if not text:
        return None

    # Skip system/command/skill-injected messages
    skip_prefixes = (
        "<local-command", "[Request interrupted", "<system-reminder",
        "<command-name", "<command-message",
        "Implement the following plan:",
        "Base directory for this skill:",
        "Unknown skill:",
    )
    if any(text.startswith(p) for p in skip_prefixes):
        return None

    # Clean up: collapse whitespace, remove newlines
    text = " ".join(text.split())
    return text


def parse_session(jsonl_path: Path) -> dict | None:
    """Parse a session JSONL file and extract metadata."""
    session_id = jsonl_path.stem
    project_dir = jsonl_path.parent

    main_size = jsonl_path.stat().st_size
    sub_dir = project_dir / session_id
    sub_size = dir_size(sub_dir) if sub_dir.is_dir() else 0
    total_size = main_size + sub_size

    cwd = None
    custom_name = None
    first_ts = None
    last_ts = None
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

                # Extract timestamp
                ts_str = entry.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except (ValueError, TypeError):
                        pass

                # Extract cwd (take the first one found)
                if cwd is None and entry.get("cwd"):
                    cwd = entry["cwd"]

                # Check for session rename
                rename_text = None
                if entry.get("type") == "system" and entry.get("subtype") == "local_command":
                    rename_text = entry.get("content", "")
                elif entry.get("type") == "user":
                    # Old format: rename stored as a short user message
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

                # Extract last meaningful user message as topic
                if entry.get("type") == "user":
                    msg = entry.get("message", {})
                    text = extract_first_user_text(msg.get("content", ""))
                    if text:
                        last_user_msg = text

                # Count user/assistant messages
                if entry.get("type") in ("user", "assistant"):
                    message_count += 1

    except Exception:
        return None

    # Derive short project path from cwd (not the dash-encoded dir name)
    if cwd:
        home = str(Path.home())
        display_path = cwd.replace(home, "~")
        # Remove common long prefixes for readability
        for prefix in ("~/Library/CloudStorage/SynologyDrive-WuNAS/", "~/SynologyDrive/WuNAS/"):
            if display_path.startswith(prefix):
                display_path = display_path[len(prefix):]
                break
        else:
            # Strip ~/
            if display_path.startswith("~/"):
                display_path = display_path[2:]
        # Keep last 2-3 meaningful components
        parts = [p for p in display_path.split("/") if p]
        if len(parts) > 3:
            short_project = "/".join(parts[-3:])
        elif len(parts) > 0:
            short_project = "/".join(parts)
        else:
            short_project = display_path
    else:
        short_project = project_dir.name

    return {
        "session_id": session_id,
        "custom_name": custom_name,
        "topic": last_user_msg,
        "project": short_project,
        "cwd": cwd or "(unknown)",
        "first_ts": first_ts,
        "last_ts": last_ts,
        "total_size": total_size,
        "message_count": message_count,
    }


def main():
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        print("No sessions found (projects directory does not exist).")
        sys.exit(0)

    # Optional filter: --project <substring>
    project_filter = None
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        if idx + 1 < len(sys.argv):
            project_filter = sys.argv[idx + 1]

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

    if not sessions:
        print("No sessions found.")
        sys.exit(0)

    # Resolve current working directory (follow symlinks) for project matching
    try:
        current_cwd = str(Path(os.getcwd()).resolve())
    except Exception:
        current_cwd = ""

    # Detect current session: most recently modified JSONL in the current project dir
    current_session_id = None
    if current_cwd:
        for s in sessions:
            session_cwd = s.get("cwd", "")
            try:
                resolved = str(Path(session_cwd).resolve()) if session_cwd else ""
            except Exception:
                resolved = session_cwd
            if resolved == current_cwd:
                # Among sessions in current project, pick the one with latest mtime
                jsonl_path = None
                for project_dir in sorted((Path.home() / ".claude" / "projects").iterdir()):
                    candidate = project_dir / f"{s['session_id']}.jsonl"
                    if candidate.exists():
                        jsonl_path = candidate
                        break
                if jsonl_path:
                    if current_session_id is None:
                        current_session_id = (s["session_id"], jsonl_path.stat().st_mtime)
                    elif jsonl_path.stat().st_mtime > current_session_id[1]:
                        current_session_id = (s["session_id"], jsonl_path.stat().st_mtime)
        current_session_id = current_session_id[0] if current_session_id else None

    # Sort by last timestamp (most recent first)
    sessions.sort(key=lambda s: s["last_ts"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # Build display name: custom name or truncated first message
    name_col_max = 28
    current_tag = "(current)"
    for s in sessions:
        is_current_session = s["session_id"] == current_session_id
        if s["custom_name"]:
            base = s["custom_name"]
        elif s["topic"]:
            base = s["topic"]
        else:
            base = "-"

        if is_current_session:
            # Truncate base name to fit "(current)" suffix within column
            max_base = name_col_max - display_width(current_tag) - 1  # 1 space before tag
            s["display_name"] = truncate(base, max_base) + " " + current_tag
        else:
            s["display_name"] = truncate(base, name_col_max)

    # Column widths (display width)
    w_name = name_col_max
    w_sid = max(max(len(s["session_id"]) for s in sessions), 2)
    w_proj = max(max(len(s["project"]) for s in sessions), 7)
    w_ts = 16
    w_size = 8
    w_msgs = 5

    # Header
    header = (
        f"{'#':>3}  "
        + pad_to_width("Name", w_name + 1)
        + f"  {'ID':<{w_sid}}"
        + f"  {pad_to_width('Project', w_proj)}"
        + f"  {'Last Active':<{w_ts}}"
        + f"  {'Size':>{w_size}}"
        + f"  {'Msgs':>{w_msgs}}"
    )
    sep = "-" * (3 + 2 + w_name + 1 + 2 + w_sid + 2 + w_proj + 2 + w_ts + 2 + w_size + 2 + w_msgs)

    print(f"Found {len(sessions)} sessions across {len(set(s['project'] for s in sessions))} projects.\n")
    print(header)
    print(sep)

    for i, s in enumerate(sessions, 1):
        ts_display = s["last_ts"].strftime("%Y-%m-%d %H:%M") if s["last_ts"] else "?"
        sid_short = s["session_id"]
        size_str = human_size(s["total_size"])
        name_display = s["display_name"]  # already truncated during build
        is_named = "*" if s["custom_name"] else " "

        # Mark project if it matches current working directory
        session_cwd = s.get("cwd", "")
        try:
            resolved_session_cwd = str(Path(session_cwd).resolve()) if session_cwd else ""
        except Exception:
            resolved_session_cwd = session_cwd
        is_current = current_cwd and resolved_session_cwd == current_cwd
        proj_marker = ">" if is_current else " "

        row = (
            f"{i:>3}  "
            + is_named + pad_to_width(name_display, w_name)
            + f"  {sid_short:<{w_sid}}"
            + f" {proj_marker}{pad_to_width(s['project'], w_proj)}"
            + f"  {ts_display:<{w_ts}}"
            + f"  {size_str:>{w_size}}"
            + f"  {s['message_count']:>{w_msgs}}"
        )
        print(row)

    # Summary
    print(sep)
    total_size = sum(s["total_size"] for s in sessions)
    named = sum(1 for s in sessions if s["custom_name"])
    has_current = any(
        str(Path(s.get("cwd", "")).resolve()) == current_cwd
        for s in sessions if s.get("cwd")
    ) if current_cwd else False
    summary = f"Total: {human_size(total_size)}  |  * = Named: {named}  |  Unnamed: {len(sessions) - named}"
    if has_current:
        summary += "  |  > = Current project"
    print(summary)


if __name__ == "__main__":
    main()
