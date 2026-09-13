#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import stat
import sys
import time
import uuid
from typing import Any, Optional

MAX_FILE_BYTES = 50 * 1024 * 1024       # 50 MB max for any DB file
MAX_JSONL_BYTES = 20 * 1024 * 1024      # 20 MB max for history.jsonl
MAX_JSON_BYTES = 1024 * 1024            # 1 MB max for JSON config/state
MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024 # 10 MB max for transcript.jsonl
MAX_SNAPSHOT_BYTES = 256 * 1024         # 256 KB max per sync snapshot
MAX_HISTORY_LINES = 25000               # Cardinality bound for history lines
MAX_LINE_BYTES = 8192                   # Line byte limit
MAX_CACHE_ENTRIES = 2000                # Max entries in model cache
MAX_CONV_DBS = 500                      # Max individual conversation DBs to scan
MAX_SCAN_SNAPSHOTS = 20                 # Max snapshot files to scan in sync dir


def safe_open_read(path: str, max_bytes: int = MAX_FILE_BYTES) -> Optional[int]:
    """
    Opens path with O_RDONLY | O_NOFOLLOW | O_CLOEXEC.
    Verifies that the file is a regular file, owned by current UID, and size <= max_bytes.
    Returns file descriptor or None if verification fails.
    Caller must close the descriptor.
    """
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            return None
        if st.st_uid != os.getuid():
            os.close(fd)
            return None
        if st.st_size > max_bytes:
            os.close(fd)
            return None
        return fd
    except Exception:
        return None


def safe_read_json(path: str, max_bytes: int = MAX_JSON_BYTES) -> Optional[Any]:
    fd = safe_open_read(path, max_bytes=max_bytes)
    if fd is None:
        return None
    try:
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes + 1)
            if len(content) > max_bytes:
                return None
            return json.loads(content)
    except Exception:
        return None


def safe_read_lines(path: str, max_bytes: int = MAX_JSONL_BYTES, max_lines: int = MAX_HISTORY_LINES, max_line_bytes: int = MAX_LINE_BYTES):
    fd = safe_open_read(path, max_bytes=max_bytes)
    if fd is None:
        return
    try:
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx >= max_lines:
                    break
                if len(line) > max_line_bytes:
                    continue
                yield line
    except Exception:
        return


def safe_sqlite_connect(db_path: str, max_bytes: int = MAX_FILE_BYTES) -> Optional[sqlite3.Connection]:
    fd = safe_open_read(db_path, max_bytes=max_bytes)
    if fd is None:
        return None
    os.close(fd)
    try:
        uri = f"file:{os.path.abspath(db_path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=3.0)
        return conn
    except Exception:
        return None


def atomic_bounded_write(target_path: str, data: str, max_bytes: int = MAX_JSON_BYTES) -> bool:
    """
    Writes data to target_path using owned no-follow descriptors and atomic replacement.
    Ensures parent directory is owned by current user and not world-writable.
    Refuses to follow symlinks at target_path.
    """
    try:
        raw_bytes = data.encode("utf-8")
        if len(raw_bytes) > max_bytes:
            sys.stderr.write(f"Payload exceeds limit of {max_bytes} bytes for {target_path}\n")
            return False

        abs_target = os.path.abspath(target_path)
        parent_dir = os.path.dirname(abs_target)
        os.makedirs(parent_dir, exist_ok=True)

        dir_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
        dir_fd = os.open(parent_dir, dir_flags)
        try:
            dir_st = os.fstat(dir_fd)
            if dir_st.st_uid != os.getuid():
                sys.stderr.write(f"Directory {parent_dir} not owned by UID {os.getuid()}\n")
                return False
            if dir_st.st_mode & 0o002:
                sys.stderr.write(f"Directory {parent_dir} is world-writable\n")
                return False

            try:
                target_st = os.lstat(abs_target)
                if stat.S_ISLNK(target_st.st_mode):
                    os.unlink(abs_target)
            except FileNotFoundError:
                pass

            filename = os.path.basename(abs_target)
            temp_name = f".{filename}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
            temp_path = os.path.join(parent_dir, temp_name)

            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            fd = os.open(temp_path, flags, 0o600)
            try:
                written = 0
                while written < len(raw_bytes):
                    n = os.write(fd, raw_bytes[written:written + 65536])
                    if n <= 0:
                        break
                    written += n
                os.fsync(fd)
            finally:
                os.close(fd)

            os.replace(temp_path, abs_target)
            return True
        finally:
            os.close(dir_fd)
    except Exception as e:
        sys.stderr.write(f"atomic_bounded_write failed for {target_path}: {e}\n")
        return False


def sync_scan(sync_dir: str, max_files: int = MAX_SCAN_SNAPSHOTS, max_file_bytes: int = MAX_SNAPSHOT_BYTES):
    """
    Safely scans sync_dir for regular .json files without following symlinks.
    Outputs each valid snapshot JSON object as a single line to stdout.
    """
    if not sync_dir or not os.path.isabs(sync_dir) or not os.path.isdir(sync_dir) or os.path.islink(sync_dir):
        return
    try:
        st = os.stat(sync_dir, follow_symlinks=False)
        if st.st_uid != os.getuid():
            return

        count = 0
        with os.scandir(sync_dir) as it:
            entries = []
            for entry in it:
                if entry.is_file(follow_symlinks=False) and re.match(r"^[A-Za-z0-9_.-]+\.json$", entry.name):
                    entries.append(entry)
            # Sort for deterministic processing
            entries.sort(key=lambda e: e.name)

            for entry in entries:
                if count >= max_files:
                    break
                data = safe_read_json(entry.path, max_bytes=max_file_bytes)
                if isinstance(data, dict) and "providers" in data:
                    line = json.dumps(data, separators=(",", ":"))
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                    count += 1
    except Exception as e:
        sys.stderr.write(f"sync_scan error: {e}\n")


def sync_write(target_path: str, max_bytes: int = MAX_SNAPSHOT_BYTES):
    """
    Reads snapshot JSON from stdin, validates it, and writes to target_path using
    atomic bounded replacement through owned no-follow descriptors.
    """
    if not target_path or not os.path.isabs(target_path):
        sys.stderr.write("sync_write: target_path must be an absolute path\n")
        sys.exit(1)
    basename = os.path.basename(target_path)
    if not re.match(r"^[A-Za-z0-9_.-]+\.json$", basename):
        sys.stderr.write(f"sync_write: invalid filename {basename}\n")
        sys.exit(1)

    raw = sys.stdin.read(max_bytes + 1)
    if len(raw) > max_bytes:
        sys.stderr.write("sync_write: stdin payload exceeded size limit\n")
        sys.exit(1)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            sys.stderr.write("sync_write: JSON payload must be an object\n")
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"sync_write: invalid JSON: {e}\n")
        sys.exit(1)

    success = atomic_bounded_write(target_path, json.dumps(data, indent=2) + "\n", max_bytes=max_bytes)
    if not success:
        sys.exit(1)


def collect():
    state_home = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    out_dir = os.path.join(state_home, "omarchy", "agents", "usage")
    os.makedirs(out_dir, exist_ok=True)

    cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    cache_path = os.path.join(cache_home, "omarchy", "antigravity-model-cache.json")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    history_paths = [
        os.path.expanduser("~/.gemini/antigravity/history.jsonl"),
        os.path.expanduser("~/.gemini/antigravity-cli/history.jsonl")
    ]
    db_paths = [
        os.path.expanduser("~/.gemini/antigravity/conversation_summaries.db"),
        os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
    ]
    settings_paths = [
        os.path.expanduser("~/.gemini/antigravity/settings.json"),
        os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
    ]
    brain_dirs = [
        os.path.expanduser("~/.gemini/antigravity/brain"),
        os.path.expanduser("~/.gemini/antigravity-cli/brain")
    ]
    conv_dirs = [
        os.path.expanduser("~/.gemini/antigravity/conversations"),
        os.path.expanduser("~/.gemini/antigravity-cli/conversations")
    ]

    conv_models = {}
    cached = safe_read_json(cache_path, max_bytes=MAX_JSON_BYTES)
    if isinstance(cached, dict):
        for k, v in list(cached.items())[:MAX_CACHE_ENTRIES]:
            if isinstance(k, str) and isinstance(v, str) and len(k) <= 128 and len(v) <= 128:
                conv_models[k] = v

    current_model = "Gemini 3.1 Pro (High)"
    for sp in settings_paths:
        sett = safe_read_json(sp, max_bytes=MAX_JSON_BYTES)
        if isinstance(sett, dict) and "model" in sett and isinstance(sett["model"], str):
            current_model = sett["model"][:128]
            break

    def get_model_for_conv(conv_id: Optional[str]) -> str:
        if not conv_id or not isinstance(conv_id, str):
            return current_model
        if not re.match(r"^[A-Za-z0-9._-]+$", conv_id):
            return current_model
        if conv_id in conv_models:
            return conv_models[conv_id]

        found_model = current_model
        for bd in brain_dirs:
            if not os.path.isdir(bd) or os.path.islink(bd):
                continue
            transcript_path = os.path.join(bd, conv_id, ".system_generated", "logs", "transcript.jsonl")
            lines = safe_read_lines(transcript_path, max_bytes=MAX_TRANSCRIPT_BYTES, max_lines=50, max_line_bytes=MAX_LINE_BYTES)
            for tline in lines:
                if "USER_SETTINGS_CHANGE" in tline and "Model Selection" in tline:
                    match = re.search(r"Model Selection` from .*? to (.*?)\. No need", tline)
                    if match:
                        found_model = match.group(1).strip()[:128]
                        break
            if found_model != current_model:
                break

        if len(conv_models) < MAX_CACHE_ENTRIES:
            conv_models[conv_id] = found_model
        return found_model

    total_sessions = 0
    total_prompts = 0
    today_prompts = 0
    today_sessions = 0

    daily_prompts = {(dt.date.today() - dt.timedelta(days=i)).isoformat(): 0 for i in range(6, -1, -1)}
    today_iso = dt.date.today().isoformat()
    month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()

    model_counts = {}
    today_model_counts = {}
    seen_convs = set()

    # 1. Use SQLite conversation_summaries.db if present
    for db_path in db_paths:
        conn = safe_sqlite_connect(db_path, max_bytes=MAX_FILE_BYTES)
        if conn is None:
            continue
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT conversation_id, step_count, substr(last_modified_time, 1, 10) "
                "FROM conversation_summaries LIMIT 10000"
            )
            for conv_id, steps, day in cur.fetchall():
                if not conv_id or conv_id in seen_convs:
                    continue
                seen_convs.add(conv_id)
                steps = max(0, min(int(steps or 0), 1000000))
                total_sessions += 1
                total_prompts += steps

                m = get_model_for_conv(conv_id)
                if m not in model_counts:
                    model_counts[m] = 0

                if day and day >= month_ago:
                    model_counts[m] = model_counts.get(m, 0) + steps

                if day:
                    daily_prompts[day] = daily_prompts.get(day, 0) + steps

                if day == today_iso:
                    today_sessions += 1
                    today_prompts += steps
                    today_model_counts[m] = today_model_counts.get(m, 0) + steps
        except Exception:
            pass
        finally:
            conn.close()

    # 2. Use individual conversation databases (*.db) for any conversations not in summaries
    for cdir in conv_dirs:
        if not os.path.isdir(cdir) or os.path.islink(cdir):
            continue
        st = os.stat(cdir, follow_symlinks=False)
        if st.st_uid != os.getuid():
            continue
        try:
            with os.scandir(cdir) as it:
                db_entries = [
                    e for e in it
                    if e.is_file(follow_symlinks=False) and re.match(r"^[A-Za-z0-9._-]+\.db$", e.name)
                ]
            db_entries.sort(key=lambda e: e.name)

            for entry in db_entries[:MAX_CONV_DBS]:
                cid = entry.name[:-3]
                if cid in seen_convs:
                    continue
                seen_convs.add(cid)

                conn = safe_sqlite_connect(entry.path, max_bytes=MAX_FILE_BYTES)
                if conn is None:
                    continue
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT count(*) FROM steps")
                    row = cur.fetchone()
                    steps = max(0, min(int(row[0] or 0), 1000000)) if row else 0
                    conn.close()

                    mtime = time.strftime("%Y-%m-%d", time.localtime(entry.stat(follow_symlinks=False).st_mtime))
                    total_sessions += 1
                    total_prompts += steps

                    m = get_model_for_conv(cid)
                    if m not in model_counts:
                        model_counts[m] = 0

                    if mtime >= month_ago:
                        model_counts[m] = model_counts.get(m, 0) + steps

                    daily_prompts[mtime] = daily_prompts.get(mtime, 0) + steps

                    if mtime == today_iso:
                        today_sessions += 1
                        today_prompts += steps
                        today_model_counts[m] = today_model_counts.get(m, 0) + steps
                except Exception:
                    pass
        except Exception:
            pass

    # 3. Parse history.jsonl for all dates to catch unflushed data
    history_daily_prompts = {}
    history_model_counts = {}
    for history_path in history_paths:
        lines = safe_read_lines(history_path, max_bytes=MAX_JSONL_BYTES, max_lines=MAX_HISTORY_LINES, max_line_bytes=MAX_LINE_BYTES)
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    continue
                timestamp_ms = record.get("timestamp", 0)
                if not isinstance(timestamp_ms, (int, float)) or timestamp_ms <= 0:
                    continue

                date_str = dt.datetime.fromtimestamp(timestamp_ms / 1000.0).date().isoformat()
                history_daily_prompts[date_str] = history_daily_prompts.get(date_str, 0) + 1

                conv_id = record.get("conversationId")
                assigned_model = get_model_for_conv(conv_id)

                if date_str not in history_model_counts:
                    history_model_counts[date_str] = {}
                history_model_counts[date_str][assigned_model] = (
                    history_model_counts[date_str].get(assigned_model, 0) + 1
                )
            except Exception:
                pass

    # Merge history with DB (take max of history vs DB per day)
    for day, h_count in history_daily_prompts.items():
        db_count = daily_prompts.get(day, 0)
        if h_count > db_count:
            diff = h_count - db_count
            if day in daily_prompts:
                daily_prompts[day] = h_count
            elif day > (dt.date.today() - dt.timedelta(days=7)).isoformat():
                daily_prompts[day] = h_count

            total_prompts += diff
            if day == today_iso:
                today_prompts = h_count

            if day >= month_ago:
                h_models = history_model_counts.get(day, {})
                for m, c in h_models.items():
                    model_counts[m] = model_counts.get(m, 0) + c
                    if day == today_iso:
                        today_model_counts[m] = today_model_counts.get(m, 0) + c

    # Save model cache atomically through owned no-follow descriptors
    atomic_bounded_write(
        cache_path,
        json.dumps(conv_models, separators=(",", ":")),
        max_bytes=MAX_JSON_BYTES
    )

    avg_tokens_per_step = 2500

    recent_days = []
    for i in range(6, -1, -1):
        day = (dt.date.today() - dt.timedelta(days=i)).isoformat()
        count = daily_prompts.get(day, 0)
        recent_days.append({
            "date": day,
            "messageCount": count * avg_tokens_per_step
        })

    model_usage_dict = {}
    for m, counts in model_counts.items():
        model_usage_dict[m] = {
            "inputTokens": int(counts * avg_tokens_per_step * 0.4),
            "outputTokens": int(counts * avg_tokens_per_step * 0.5),
            "cacheTokens": int(counts * avg_tokens_per_step * 0.1),
            "totalTokens": counts * avg_tokens_per_step
        }

    today_tokens_by_model = {}
    for m, counts in today_model_counts.items():
        if counts == 0:
            continue
        today_tokens_by_model[m] = {
            "inputTokens": int(counts * avg_tokens_per_step * 0.4),
            "outputTokens": int(counts * avg_tokens_per_step * 0.5),
            "cacheTokens": int(counts * avg_tokens_per_step * 0.1),
            "totalTokens": counts * avg_tokens_per_step
        }

    if today_prompts > 0 and not today_tokens_by_model:
        today_tokens_by_model[current_model] = {
            "inputTokens": 1000,
            "outputTokens": 1500,
            "cacheTokens": 0,
            "totalTokens": 2500
        }

    data = {
        "id": "antigravity",
        "name": "Antigravity",
        "schemaVersion": 1,
        "ready": True,
        "hasLocalStats": True,
        "usageStatusText": "Active",
        "activeDates": [],
        "activeDays": 0,
        "authHelpText": "",
        "limits": [],
        "modelUsage": model_usage_dict,
        "recentDays": recent_days,
        "todayPrompts": today_prompts,
        "todaySessions": today_sessions,
        "todayTokensByModel": today_tokens_by_model,
        "todayTotalTokens": today_prompts * avg_tokens_per_step,
        "totalPrompts": total_prompts,
        "totalSessions": total_sessions,
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat()
    }

    out_file = os.path.join(out_dir, "antigravity.json")
    success = atomic_bounded_write(
        out_file,
        json.dumps(data, indent=2) + "\n",
        max_bytes=MAX_JSON_BYTES
    )
    if not success:
        sys.stderr.write(f"Failed to write usage record to {out_file}\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Collect Antigravity usage metrics safely.")
    parser.add_argument("--force", action="store_true", help="Force full refresh")
    parser.add_argument("--limits-only", action="store_true", help="Refresh limits only")
    parser.add_argument("--except", dest="exclude", action="append", help="Exclude provider ID")
    parser.add_argument("--sync-scan", dest="sync_scan_dir", help="Safely scan directory for snapshot JSONs")
    parser.add_argument("--sync-write", dest="sync_write_path", help="Safely write snapshot JSON from stdin")
    parser.add_argument("agents", nargs="*", help="Specific agent IDs to refresh")

    args = parser.parse_args()

    if args.sync_scan_dir:
        sync_scan(args.sync_scan_dir)
        return

    if args.sync_write_path:
        sync_write(args.sync_write_path)
        return

    collect()


if __name__ == "__main__":
    main()
