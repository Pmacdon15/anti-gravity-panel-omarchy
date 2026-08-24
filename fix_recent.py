import re

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py', 'r') as f:
    content = f.read()

old_recent = """recent_days = []
for day_str in sorted(daily_prompts.keys()):
    recent_days.append({
        "date": day_str,
        "messageCount": daily_prompts[day_str] * avg_tokens_per_step
    })"""

new_recent = """recent_days = []
weekly_prompts = 0
import datetime as dt_temp
for i in range(6, -1, -1):
    day = (dt_temp.date.today() - dt_temp.timedelta(days=i)).isoformat()
    count = daily_prompts.get(day, 0)
    weekly_prompts += count
    recent_days.append({
        "date": day,
        "messageCount": count * avg_tokens_per_step
    })"""

content = content.replace(old_recent, new_recent)

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py', 'w') as f:
    f.write(content)

