import json
import os
import datetime as dt
import re
import sqlite3

out_dir = os.path.expanduser("~/.local/state/omarchy/agents/usage")
os.makedirs(out_dir, exist_ok=True)

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
cache_path = os.path.expanduser("~/.cache/omarchy/antigravity-model-cache.json")
brain_dirs = [
    os.path.expanduser("~/.gemini/antigravity/brain"),
    os.path.expanduser("~/.gemini/antigravity-cli/brain")
]
conv_dirs = [
    os.path.expanduser("~/.gemini/antigravity/conversations"),
    os.path.expanduser("~/.gemini/antigravity-cli/conversations")
]

os.makedirs(os.path.dirname(cache_path), exist_ok=True)

conv_models = {}
if os.path.exists(cache_path):
    try:
        with open(cache_path, 'r') as f:
            conv_models = json.load(f)
    except Exception:
        pass

current_model = "Gemini 3.1 Pro (High)"
for sp in settings_paths:
    if os.path.exists(sp):
        try:
            with open(sp, 'r') as f:
                sett = json.load(f)
                if "model" in sett:
                    current_model = sett["model"]
                    break
        except Exception:
            pass

def get_model_for_conv(conv_id):
    if not conv_id:
        return current_model
    if conv_id in conv_models:
        return conv_models[conv_id]
        
    found_model = current_model
    for bd in brain_dirs:
        transcript_path = os.path.join(bd, conv_id, ".system_generated", "logs", "transcript.jsonl")
        if os.path.exists(transcript_path):
            try:
                with open(transcript_path, 'r') as tf:
                    for i, tline in enumerate(tf):
                        if i > 50: break
                        if "USER_SETTINGS_CHANGE" in tline and "Model Selection" in tline:
                            match = re.search(r"Model Selection` from .*? to (.*?)\. No need", tline)
                            if match:
                                found_model = match.group(1).strip()
                                break
            except Exception:
                pass
            break
            
    conv_models[conv_id] = found_model
    return found_model

total_sessions = 0
total_prompts = 0
today_prompts = 0
today_sessions = 0

daily_prompts = { (dt.date.today() - dt.timedelta(days=i)).isoformat(): 0 for i in range(6, -1, -1) }
today_iso = dt.date.today().isoformat()
month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()

model_counts = {}
today_model_counts = {}
seen_convs = set()

# 1. Use SQLite conversation_summaries.db if present
for db_path in db_paths:
    if not os.path.exists(db_path): continue
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT conversation_id, step_count, substr(last_modified_time, 1, 10) FROM conversation_summaries")
    for conv_id, steps, day in cur.fetchall():
        if conv_id in seen_convs: continue
        seen_convs.add(conv_id)
        steps = steps or 0
        total_sessions += 1
        total_prompts += steps
        
        m = get_model_for_conv(conv_id)
        if m not in model_counts:
            model_counts[m] = 0
            
        if day >= month_ago:
            model_counts[m] = model_counts.get(m, 0) + steps
            
        daily_prompts[day] = daily_prompts.get(day, 0) + steps
        
        if day == today_iso:
            today_sessions += 1
            today_prompts += steps
            today_model_counts[m] = today_model_counts.get(m, 0) + steps
    conn.close()

# 2. Use individual conversation databases (*.db) for any conversations not in summaries
import glob, time
for cdir in conv_dirs:
    if not os.path.exists(cdir): continue
    for db_file in glob.glob(os.path.join(cdir, "*.db")):
        cid = os.path.basename(db_file)[:-3]
        if cid in seen_convs: continue
        seen_convs.add(cid)
        try:
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM steps")
            steps = cur.fetchone()[0] or 0
            conn.close()
            mtime = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(db_file)))
            
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

# 3. Parse history.jsonl for all dates to catch unflushed data
history_daily_prompts = {}
history_model_counts = {}
for history_path in history_paths:
    if os.path.exists(history_path):
        with open(history_path, 'r') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    record = json.loads(line)
                    timestamp_ms = record.get("timestamp", 0)
                    if timestamp_ms == 0: continue
                    
                    date_str = dt.datetime.fromtimestamp(timestamp_ms / 1000.0).date().isoformat()
                    history_daily_prompts[date_str] = history_daily_prompts.get(date_str, 0) + 1
                    
                    conv_id = record.get("conversationId")
                    assigned_model = get_model_for_conv(conv_id)
                    
                    if date_str not in history_model_counts:
                        history_model_counts[date_str] = {}
                    history_model_counts[date_str][assigned_model] = history_model_counts[date_str].get(assigned_model, 0) + 1
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
            
        # Update model counts for this diff
        if day >= month_ago:
            h_models = history_model_counts.get(day, {})
            for m, c in h_models.items():
                model_counts[m] = model_counts.get(m, 0) + c
                if day == today_iso:
                    today_model_counts[m] = today_model_counts.get(m, 0) + c


with open(cache_path, 'w') as f:
    json.dump(conv_models, f)

avg_tokens_per_step = 2500

recent_days = []
import datetime as dt_temp
for i in range(6, -1, -1):
    day = (dt_temp.date.today() - dt_temp.timedelta(days=i)).isoformat()
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
    if counts == 0: continue
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
    "modelUsage"  : model_usage_dict,
    "recentDays": recent_days,
    "todayPrompts": today_prompts,
    "todaySessions": today_sessions,
    "todayTokensByModel": today_tokens_by_model,
    "todayTotalTokens": today_prompts * avg_tokens_per_step,
    "totalPrompts": total_prompts,
    "totalSessions": total_sessions,
    "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat()
}

with open(os.path.join(out_dir, "antigravity.json"), "w") as f:
    json.dump(data, f)
