import sys
import re
import datetime as dt

script_path = '/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py'
with open(script_path, 'r') as f:
    content = f.read()

# We need to filter the model_counts loop to only include the last 30 days.
old_loop = """for row in c.fetchall():
    conv_id = row[0]
    total_prompts += 1
    total_sessions.add(conv_id)
    
    timestamp = row[2]
    # parse timestamp (e.g. 2026-07-09T01:55:00Z)
    try:
        date_str = timestamp.split('T')[0]
        daily_prompts[date_str] = daily_prompts.get(date_str, 0) + 1
        active_dates.add(date_str)
        
        assigned_model = get_model_for_conv(conv_id)
        model_counts[assigned_model] = model_counts.get(assigned_model, 0) + 1
        
        if date_str == today_iso:
            today_prompts += 1
            today_sessions.add(conv_id)
            today_model_counts[assigned_model] = today_model_counts.get(assigned_model, 0) + 1
    except Exception:
        pass"""

new_loop = """month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()
for row in c.fetchall():
    conv_id = row[0]
    total_prompts += 1
    total_sessions.add(conv_id)
    
    timestamp = row[2]
    try:
        date_str = timestamp.split('T')[0]
        daily_prompts[date_str] = daily_prompts.get(date_str, 0) + 1
        active_dates.add(date_str)
        
        # Only aggregate model usage for the trailing 30 days!
        if date_str >= month_ago:
            assigned_model = get_model_for_conv(conv_id)
            model_counts[assigned_model] = model_counts.get(assigned_model, 0) + 1
        
        if date_str == today_iso:
            today_prompts += 1
            today_sessions.add(conv_id)
            today_model_counts[assigned_model] = today_model_counts.get(assigned_model, 0) + 1
    except Exception:
        pass"""

content = content.replace(old_loop, new_loop)

# Also fix the history parser to only include trailing 30 days for models!
old_history_loop = """# Merge history with DB (take max of history vs DB per day)
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
                today_model_counts[m] = today_model_counts.get(m, 0) + c"""

new_history_loop = """# Merge history with DB (take max of history vs DB per day)
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
                    today_model_counts[m] = today_model_counts.get(m, 0) + c"""

content = content.replace(old_history_loop, new_history_loop)

with open(script_path, 'w') as f:
    f.write(content)
