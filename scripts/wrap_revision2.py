"""Wrap each clip-mutation endpoint with baseRevision check."""
path = 'yroll/server/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Each endpoint signature: def NAME(req, ...) with sessionId. We add baseRevision.
# And the body uses guard(_do) - we change to guard(_check_rev(baseRevision, _do))

# Use a regex per endpoint
import re
for ep in [
    ('move_clip', '"move_clip(clip_id: str, req: MoveReq"'),
    ('trim_clip', '"trim_clip(clip_id: str, req: TrimReq"'),
    ('split_clip', '"split_clip(clip_id: str, req: SplitReq"'),
]:
    name, sig = ep
    # find: def name(...sessionId: str = ""):\n...guard(_do)
    pattern = re.compile(
        r'(def ' + name + r'\(' + re.escape(sig[1:]) + r'.*?sessionId: str = ""\):)'
        r'(.*?return guard\(_do\))',
        re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        print(f'  NOT FOUND: {name}')
        continue
    old = m.group(0)
    # Insert baseRevision param and wrap
    new = old.replace(
        'sessionId: str = ""):',
        'sessionId: str = "", baseRevision: int = None):'
    ).replace(
        'return guard(_do)',
        'return guard(_check_rev(baseRevision, _do))'
    )
    content = content.replace(old, new, 1)
    print(f'  wrapped: {name}')

# Also wrap remove_clip (DELETE)
m = re.search(
    r'(def remove_clip\(clip_id: str.*?sessionId: str = ""\),)\n(.*?)(return guard\(_do\))',
    content, re.DOTALL
)
if m:
    old = m.group(0)
    new = old.replace('sessionId: str = ""),', 'sessionId: str = "", baseRevision: int = None),'
    content = content.replace(old, new, 1)
    print('  wrapped: remove_clip')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
