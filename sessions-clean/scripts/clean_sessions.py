#!/usr/bin/env python3
"""Identify Claude Code sessions for cleanup. Outputs JSON for Claude to act on."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone


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


def parse_session_basic(jsonl_path: Path) -> dict | None:
    """Parse minimal session info for cleanup decisions."""
    session_id = jsonl_path.stem
    project_dir = jsonl_path.parent

    main_size = jsonl_path.stat().st_size
    sub_dir = project_dir / session_id
    sub_size = dir_size(sub_dir) if sub_dir.is_dir() else 0
    total_size = main_size + sub_size

    custom_name = None
    last_user_msg = None
    last_ts = None

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

    except Exception:
        return None

    # Build display name: custom name > first user message > (unnamed)
    if custom_name:
        display_name = custom_name
    elif last_user_msg:
        display_name = last_user_msg[:60] + "…" if len(last_user_msg) > 60 else last_user_msg
    else:
        display_name = "(unnamed)"

    # Files to delete
    paths_to_delete = [str(jsonl_path)]
    if sub_dir.is_dir():
        paths_to_delete.append(str(sub_dir))

    return {
        "session_id": session_id,
        "name": display_name,
        "is_named": custom_name is not None,
        "project_dir": str(project_dir),
        "last_ts": last_ts.isoformat() if last_ts else None,
        "total_size": total_size,
        "total_size_human": human_size(total_size),
        "paths_to_delete": paths_to_delete,
    }


def find_matches(target: str, all_sessions: list[dict]) -> tuple[str, list[dict]]:
    """Find sessions matching a target string by ID prefix or name.
    Returns (match_type, matched_sessions)."""
    # 1. ID prefix match
    matched = [s for s in all_sessions if s["session_id"].startswith(target)]
    if matched:
        return ("id_prefix", matched)

    # 2. Exact name match (case-insensitive)
    matched = [s for s in all_sessions if s["name"].lower() == target.lower()]
    if matched:
        return ("name_exact", matched)

    # 3. Name substring match (case-insensitive)
    matched = [s for s in all_sessions if target.lower() in s["name"].lower()]
    if matched:
        return ("name_substring", matched)

    return ("no_match", [])


def detect_current_session(projects_dir: Path) -> str | None:
    """Detect the current session ID based on cwd and most recent mtime."""
    try:
        current_cwd = str(Path(os.getcwd()).resolve())
    except Exception:
        return None

    if not current_cwd:
        return None

    best_mtime = 0.0
    current_session_id = None
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            if jsonl_file.parent != project_dir:
                continue
            mtime = jsonl_file.stat().st_mtime
            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        cwd = entry.get("cwd")
                        if cwd:
                            try:
                                resolved = str(Path(cwd).resolve())
                            except Exception:
                                resolved = cwd
                            if resolved == current_cwd and mtime > best_mtime:
                                best_mtime = mtime
                                current_session_id = jsonl_file.stem
                            break
            except Exception:
                pass

    return current_session_id


def collect_all_sessions(projects_dir: Path, current_session_id: str | None) -> list[dict]:
    """Parse all sessions, excluding the current one."""
    sessions = []
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            if jsonl_file.parent != project_dir:
                continue
            info = parse_session_basic(jsonl_file)
            if not info:
                continue
            if info["session_id"] == current_session_id:
                continue
            sessions.append(info)
    return sessions


def main():
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        print(json.dumps({"error": "No projects directory found", "sessions": []}))
        sys.exit(0)

    # Parse arguments
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args or (len(args) == 1 and args[0] in ("empty", "unnamed")):
        mode = args[0] if args else "empty"
    else:
        mode = "targeted"

    current_session_id = detect_current_session(projects_dir)
    all_sessions = collect_all_sessions(projects_dir, current_session_id)

    if mode == "targeted":
        targets = args
        target_results = []
        seen_ids = set()
        resolved_sessions = []

        for target in targets:
            match_type, matched = find_matches(target, all_sessions)
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

        # Sort resolved sessions by last_ts (oldest first)
        resolved_sessions.sort(key=lambda s: s["last_ts"] or "")

        total_size = sum(s["total_size"] for s in resolved_sessions)
        result = {
            "mode": "targeted",
            "target_results": target_results,
            "count": len(resolved_sessions),
            "total_size": total_size,
            "total_size_human": human_size(total_size),
            "sessions": resolved_sessions,
        }
    else:
        sessions = []
        for s in all_sessions:
            if mode == "unnamed":
                if not s["is_named"]:
                    sessions.append(s)
            elif mode == "empty":
                if not s["is_named"] and s["total_size"] <= 10240:
                    sessions.append(s)

        # Sort by last_ts (oldest first)
        sessions.sort(key=lambda s: s["last_ts"] or "")

        total_size = sum(s["total_size"] for s in sessions)
        result = {
            "mode": mode,
            "count": len(sessions),
            "total_size": total_size,
            "total_size_human": human_size(total_size),
            "sessions": sessions,
        }

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
