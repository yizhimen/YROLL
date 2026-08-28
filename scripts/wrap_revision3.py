path = 'yroll/server/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

import re

endpoints = ['move_clip', 'trim_clip', 'split_clip']
for name in endpoints:
    # Find the def line
    pattern = re.compile(
        r'(def ' + name + r'\([^)]*?sessionId: str = ""\))(.*?)(return guard\(_do\))',
        re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        print(f'  NOT FOUND: {name}')
        continue
    old = m.group(0)
    new = old.replace(
        'sessionId: str = ""',
        'sessionId: str = "", baseRevision: int = None',
        1
    ).replace(
        'return guard(_do)',
        'return guard(_check_rev(baseRevision, _do))',
        1
    )
    content = content.replace(old, new, 1)
    print(f'  wrapped: {name}')

# remove_clip (DELETE)
m = re.search(
    r'(def remove_clip\(.*?sessionId: str = ""\),)\n(.*?)(return guard\(_do\))',
    content, re.DOTALL
)
if m:
    old = m.group(0)
    new = old.replace('sessionId: str = ""),', 'sessionId: str = "", baseRevision: int = None),', 1)
    content = content.replace(old, new, 1)
    print('  wrapped: remove_clip')
else:
    print('  NOT FOUND: remove_clip')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
