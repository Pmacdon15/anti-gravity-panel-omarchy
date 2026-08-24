import re

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py', 'r') as f:
    content = f.read()

old_db_loop = """    for conv_id, steps, day in cur.fetchall():
        steps = steps or 0
        total_sessions += 1
        total_prompts += steps
        
        m = get_model_for_conv(conv_id)
        
        if day >= month_ago:
            model_counts[m] = model_counts.get(m, 0) + steps
            
        daily_prompts[day] = daily_prompts.get(day, 0) + steps"""

new_db_loop = """    for conv_id, steps, day in cur.fetchall():
        steps = steps or 0
        total_sessions += 1
        total_prompts += steps
        
        m = get_model_for_conv(conv_id)
        
        # Ensure the model exists in the dictionary, even if 0
        if m not in model_counts:
            model_counts[m] = 0
            
        if day >= month_ago:
            model_counts[m] = model_counts.get(m, 0) + steps
            
        daily_prompts[day] = daily_prompts.get(day, 0) + steps"""

content = content.replace(old_db_loop, new_db_loop)

# I also need to remove the "if counts == 0: continue" from the model_usage_dict loop!
old_dict_loop = """model_usage_dict = {}
for m, counts in model_counts.items():
    if counts == 0: continue
    model_usage_dict[m] = {"""

new_dict_loop = """model_usage_dict = {}
for m, counts in model_counts.items():
    model_usage_dict[m] = {"""

content = content.replace(old_dict_loop, new_dict_loop)

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/collect-antigravity.py', 'w') as f:
    f.write(content)

