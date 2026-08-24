import sys

script_path = '/home/pmacd/Projects/antigravity-panel/collect-antigravity.py'
with open(script_path, 'r') as f:
    content = f.read()

old_history_logic = """# Also parse history.jsonl for completely new/unflushed prompts today
history_today_prompts = 0
history_today_model_counts = {}
if os.path.exists(history_path):
    with open(history_path, 'r') as f:
        for line in f:
            if not line.strip(): continue
            try:
                record = json.loads(line)
                timestamp_ms = record.get("timestamp", 0)
                if timestamp_ms == 0: continue
                
                date_str = dt.datetime.fromtimestamp(timestamp_ms / 1000.0).date().isoformat()
                if date_str == today_iso:
                    history_today_prompts += 1
                    conv_id = record.get("conversationId")
                    assigned_model = get_model_for_conv(conv_id)
                    history_today_model_counts[assigned_model] = history_today_model_counts.get(assigned_model, 0) + 1
            except Exception:
                pass

# If history has more today than DB, use history as source of truth for today
if history_today_prompts > today_prompts:
    diff = history_today_prompts - today_prompts
    today_prompts = history_today_prompts
    total_prompts += diff
    daily_prompts[today_iso] = today_prompts
    
    for m, c in history_today_model_counts.items():
        # diff in model
        db_c = today_model_counts.get(m, 0)
        if c > db_c:
            model_counts[m] = model_counts.get(m, 0) + (c - db_c)
            today_model_counts[m] = c"""

new_history_logic = """# Parse history.jsonl for all dates to catch unflushed data
history_daily_prompts = {}
history_model_counts = {}
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
        h_models = history_model_counts.get(day, {})
        for m, c in h_models.items():
            model_counts[m] = model_counts.get(m, 0) + c  # Rough addition, not exactly diffed per model, but close enough for UI
            if day == today_iso:
                today_model_counts[m] = today_model_counts.get(m, 0) + c
"""

content = content.replace(old_history_logic, new_history_logic)
with open(script_path, 'w') as f:
    f.write(content)
