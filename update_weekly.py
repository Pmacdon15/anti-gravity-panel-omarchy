import sys
import re

script_path = '/home/pmacd/Projects/antigravity-panel/collect-antigravity.py'
with open(script_path, 'r') as f:
    content = f.read()

# I need to insert a weekly_prompts calculation before the limits array
insert_pos = content.find('model_usage_dict = {}')

weekly_calc = """weekly_prompts = sum(daily_prompts.values())
"""

content = content[:insert_pos] + weekly_calc + content[insert_pos:]

# Now replace total_prompts with weekly_prompts in the weekly limit
old_weekly = '{"label": "Weekly quota", "type": "tokens", "resetsAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat(), "percent": (total_prompts * avg_tokens_per_step) / max(1, max(10000000, total_prompts * avg_tokens_per_step + 2000000))}'
new_weekly = '{"label": "Weekly quota", "type": "tokens", "resetsAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat(), "percent": (weekly_prompts * avg_tokens_per_step) / max(1, max(10000000, weekly_prompts * avg_tokens_per_step + 2000000))}'

content = content.replace(old_weekly, new_weekly)

with open(script_path, 'w') as f:
    f.write(content)
