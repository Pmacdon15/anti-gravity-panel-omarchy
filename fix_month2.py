import re

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py', 'r') as f:
    content = f.read()

# Replace the DB loop
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
            today_sessions += 1
            today_prompts += steps
            today_model_counts[m] = today_model_counts.get(m, 0) + steps"""

content = re.sub(r'    for conv_id, steps, day in cur.fetchall\(\):.*?    conn\.close\(\)', new_db_loop + '\n    conn.close()', content, flags=re.DOTALL)

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py', 'w') as f:
    f.write(content)

