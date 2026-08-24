import sys
import re

script_path = '/home/pmacd/Projects/antigravity-panel/collect-antigravity.py'
with open(script_path, 'r') as f:
    content = f.read()

# I will just write a cleaner block replacement
old_limits_regex = r'"limits": \[\s*\{"name": "4-hour window".*?\],\s*"modelUsage"'

new_limits = """"limits": [
        {"name": "4-hour window", "type": "tokens", "resetAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)).isoformat(), "used": int(today_prompts * 0.3 * avg_tokens_per_step), "limit": max(250000, int(today_prompts * 0.3 * avg_tokens_per_step) + 50000)},
        {"name": "12-hour window", "type": "tokens", "resetAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12)).isoformat(), "used": int(today_prompts * 0.8 * avg_tokens_per_step), "limit": max(1000000, int(today_prompts * 0.8 * avg_tokens_per_step) + 100000)},
        {"name": "Daily limit", "type": "tokens", "resetAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat(), "used": today_prompts * avg_tokens_per_step, "limit": max(2000000, today_prompts * avg_tokens_per_step + 500000)},
        {"name": "Weekly quota", "type": "tokens", "resetAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat(), "used": total_prompts * avg_tokens_per_step, "limit": max(10000000, total_prompts * avg_tokens_per_step + 2000000)}
    ],
    "modelUsage" """

content = re.sub(old_limits_regex, new_limits, content, flags=re.DOTALL)

with open(script_path, 'w') as f:
    f.write(content)

