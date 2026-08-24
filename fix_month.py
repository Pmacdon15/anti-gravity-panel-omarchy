import sys

script_path = '/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py'
with open(script_path, 'r') as f:
    content = f.read()

# Define month_ago at the top
month_def = "month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()\n"
content = content.replace("today_iso = dt.date.today().isoformat()", "today_iso = dt.date.today().isoformat()\n" + month_def)

old_db_loop = """    for conv_id, steps, day in cur.fetchall():
        steps = steps or 0
        total_sessions += 1
        total_prompts += steps
        
        m = get_model_for_conv(conv_id)
        model_counts[m] = model_counts.get(m, 0) + steps
        daily_prompts[day] = daily_prompts.get(day, 0) + steps
        active_dates.add(day)
        
        if day == today_iso:
            today_prompts += steps
            today_sessions += 1
            today_model_counts[m] = today_model_counts.get(m, 0) + steps"""

new_db_loop = """    for conv_id, steps, day in cur.fetchall():
        steps = steps or 0
        total_sessions += 1
        total_prompts += steps
        
        m = get_model_for_conv(conv_id)
        if day >= month_ago:
            model_counts[m] = model_counts.get(m, 0) + steps
            
        daily_prompts[day] = daily_prompts.get(day, 0) + steps
        active_dates.add(day)
        
        if day == today_iso:
            today_prompts += steps
            today_sessions += 1
            today_model_counts[m] = today_model_counts.get(m, 0) + steps"""

content = content.replace(old_db_loop, new_db_loop)

with open(script_path, 'w') as f:
    f.write(content)
