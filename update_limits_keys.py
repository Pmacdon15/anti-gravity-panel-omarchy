import sys
import re

script_path = '/home/pmacd/Projects/antigravity-panel/collect-antigravity.py'
with open(script_path, 'r') as f:
    content = f.read()

# Replace the limits list again
old_limits_regex = r'"limits": \[\s*\{"name": "4-hour window".*?\],\s*"modelUsage"'

new_limits = """"limits": [
        {"label": "4-hour window", "type": "tokens", "resetsAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)).isoformat(), "percent": int(today_prompts * 0.3 * avg_tokens_per_step) / max(1, max(250000, int(today_prompts * 0.3 * avg_tokens_per_step) + 50000))},
        {"label": "12-hour window", "type": "tokens", "resetsAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12)).isoformat(), "percent": int(today_prompts * 0.8 * avg_tokens_per_step) / max(1, max(1000000, int(today_prompts * 0.8 * avg_tokens_per_step) + 100000))},
        {"label": "Daily limit", "type": "tokens", "resetsAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat(), "percent": (today_prompts * avg_tokens_per_step) / max(1, max(2000000, today_prompts * avg_tokens_per_step + 500000))},
        {"label": "Weekly quota", "type": "tokens", "resetsAt": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat(), "percent": (total_prompts * avg_tokens_per_step) / max(1, max(10000000, total_prompts * avg_tokens_per_step + 2000000))}
    ],
    "modelUsage" """

content = re.sub(old_limits_regex, new_limits, content, flags=re.DOTALL)

with open(script_path, 'w') as f:
    f.write(content)

