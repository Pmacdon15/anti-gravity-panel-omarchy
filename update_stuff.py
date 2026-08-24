import sys
import json

# 1. Update manifest.json
with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/manifest.json', 'r') as f:
    manifest = json.load(f)

manifest['barWidget']['defaultSection'] = "right"

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)

# 2. Update Panel.qml Header
with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/Panel.qml', 'r') as f:
    content = f.read()

content = content.replace('text: "TOKENS BY MODEL"', 'text: "ALL-TIME TOKENS BY MODEL"')

with open('/home/pmacd/Projects/anti-gravity-panel-omarchy/Panel.qml', 'w') as f:
    f.write(content)
