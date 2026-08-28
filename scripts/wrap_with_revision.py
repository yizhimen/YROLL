"""Wrap key mutations with baseRevision check."""
import re
path = 'yroll/server/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Helper that wraps endpoint to do revision check + return 409 on conflict
helper_code = '''

    def _check_rev(baseRevision, fn):
        """Decorator-equivalent: check revision before calling fn, return 409 on conflict."""
        def _do(*args, **kwargs):
            if baseRevision is not None:
                try:
                    check_project_revision(st.core, baseRevision)
                except ProjectRevisionConflict as e:
                    raise HTTPException(409, str(e)) from e
            return fn(*args, **kwargs)
        return _do
'''
# Insert after guard + require_revision
old = '''    def require_revision(fn):
        """Wrap mutation: verify baseRevision query param matches server, else 409."""
        def _do(*args, **kwargs):
            base_rev = kwargs.pop('baseRevision', None)
            # args/kwargs may have baseRevision for endpoints that take it
            if base_rev is None and len(args) > 0 and isinstance(args[0], (int, float)):
                # Try to read from query-like position
                pass
            return fn(*args, **kwargs)
        return _do'''
new = old + helper_code
if '_check_rev' not in content:
    content = content.replace(old, new)
    print('1: _check_rev helper added')

# Wrap key mutations: add `baseRevision: int = None` and call _check_rev
# Pattern: replace `def FUNC(...): return guard(lambda: st.cmd.X(...))`
# with: `def FUNC(..., baseRevision: int = None): return guard(_check_rev(baseRevision, lambda: st.cmd.X(...)))`

endpoints_to_wrap = [
    # (signature_pattern, replace_with)
    # add_clip
    ('''    @app.post("/clips")
    def add_clip(req: AddClipReq, sessionId: str = ""):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.add_clip(**req.model_dump())
        return guard(_do)''',
     '''    @app.post("/clips")
    def add_clip(req: AddClipReq, sessionId: str = "", baseRevision: int = None):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.add_clip(**req.model_dump())
        return guard(_check_rev(baseRevision, _do))'''),
    # move_clip
    ('''    @app.post("/clips/{clip_id}/move")
    def move_clip(clip_id: str, req: MoveReq, sessionId: str = ""):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.move_clip(clip_id=clip_id, **req.model_dump())
        return guard(_do)''',
     '''    @app.post("/clips/{clip_id}/move")
    def move_clip(clip_id: str, req: MoveReq, sessionId: str = "", baseRevision: int = None):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.move_clip(clip_id=clip_id, **req.model_dump())
        return guard(_check_rev(baseRevision, _do))'''),
    # trim_clip
    ('''    @app.post("/clips/{clip_id}/trim")
    def trim_clip(clip_id: str, req: TrimReq, sessionId: str = ""):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.trim_clip(clip_id=clip_id, **req.model_dump())
        return guard(_do)''',
     '''    @app.post("/clips/{clip_id}/trim")
    def trim_clip(clip_id: str, req: TrimReq, sessionId: str = "", baseRevision: int = None):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.trim_clip(clip_id=clip_id, **req.model_dump())
        return guard(_check_rev(baseRevision, _do))'''),
    # split_clip
    ('''    @app.post("/clips/{clip_id}/split")
    def split_clip(clip_id: str, req: SplitReq, sessionId: str = ""):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.split_clip(clip_id=clip_id, **req.model_dump())
        return guard(_do)''',
     '''    @app.post("/clips/{clip_id}/split")
    def split_clip(clip_id: str, req: SplitReq, sessionId: str = "", baseRevision: int = None):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.split_clip(clip_id=clip_id, **req.model_dump())
        return guard(_check_rev(baseRevision, _do))'''),
    # remove_clip
    ('''    @app.delete("/clips/{clip_id}")
    def remove_clip(clip_id: str, ripple: bool = False, why: str = "API 删除",
                    sessionId: str = ""):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.remove_clip(clip_id, why=why, ripple=ripple)
        return guard(_do)''',
     '''    @app.delete("/clips/{clip_id}")
    def remove_clip(clip_id: str, ripple: bool = False, why: str = "API 删除",
                    sessionId: str = "", baseRevision: int = None):
        def _do():
            if sessionId:
                require_edit_right(st.core, sessionId)
            return st.cmd.remove_clip(clip_id, why=why, ripple=ripple)
        return guard(_check_rev(baseRevision, _do))'''),
]

for old_pat, new_pat in endpoints_to_wrap:
    if old_pat in content:
        content = content.replace(old_pat, new_pat, 1)
        print(f'wrapped: {new_pat[:60]}...')
    else:
        print(f'NOT FOUND: {old_pat[:60]}...')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
