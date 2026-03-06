#!/usr/bin/env python3
"""List all Claude Code sessions with metadata. Outputs JSON for Claude to format."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
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
    """Extract plain text from user message content (str or list)."""
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

    # Derive short project path from cwd
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
        elif len(parts) > 0:
            short_project = "/".join(parts)
        else:
            short_project = display_path
    else:
        short_project = project_dir.name

    # Build display name
    if custom_name:
        display_name = custom_name
    elif last_user_msg:
        display_name = last_user_msg[:60] + "…" if len(last_user_msg) > 60 else last_user_msg
    else:
        display_name = "-"

    return {
        "session_id": session_id,
        "name": display_name,
        "is_named": custom_name is not None,
        "project": short_project,
        "cwd": cwd or "(unknown)",
        "is_current_project": False,  # filled in later
        "is_current_session": False,  # filled in later
        "last_ts": last_ts.isoformat() if last_ts else None,
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "message_count": message_count,
    }


def main():
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        print(json.dumps({"error": "No projects directory found", "count": 0, "sessions": []}))
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
        print(json.dumps({"count": 0, "total_size": 0, "total_size_human": "0 B", "sessions": []}))
        sys.exit(0)

    # Resolve current working directory for project matching
    try:
        current_cwd = str(Path(os.getcwd()).resolve())
    except Exception:
        current_cwd = ""

    # Detect current session and mark current project
    current_session_id = None
    if current_cwd:
        best_mtime = 0.0
        for s in sessions:
            session_cwd = s.get("cwd", "")
            try:
                resolved = str(Path(session_cwd).resolve()) if session_cwd else ""
            except Exception:
                resolved = session_cwd
            if resolved == current_cwd:
                s["is_current_project"] = True
                # Find the JSONL file to check mtime
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

    # Sort by last timestamp (most recent first)
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
        "sessions": sessions,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
