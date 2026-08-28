"""Add lease endpoints to server app.py"""
path = 'yroll/server/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_imp = 'from yroll.core.manifest import Actor, Region, TimeRange'
new_imp = '''from yroll.core.manifest import Actor, Region, TimeRange
from yroll.core.lease import (
    LeaseStore, LeaseMode, Actor as LeaseActor,
    LeaseError, LeaseConflictError, LeaseExpiredError,
    get_lease_store, require_edit_right, get_current_revision,
    check_revision_match,
)'''
if old_imp in content and 'get_lease_store' not in content:
    content = content.replace(old_imp, new_imp)
    print('1: imports added')

marker = '    # ---------- 本地字体导入 ----------'
if marker in content and '/lease' not in content:
    lease_endpoints = '''    # ---------- Edit Lease (P0-10): editing-rights management ----------
    @app.get("/lease")
    def get_lease():
        ls = get_lease_store(st.core).get(st.core.project.project_id)
        if ls is None:
            return {"heldBy": None, "sessionId": None, "mode": None,
                    "actor": None, "baseRevision": get_current_revision(st.core),
                    "isAlive": False, "humanLabel": ""}
        return {"heldBy": ls.actor.value, "sessionId": ls.session_id,
                "mode": ls.mode.value, "actor": ls.actor.value,
                "baseRevision": ls.base_revision, "isAlive": ls.is_alive(LeaseStore.HEARTBEAT_TTL),
                "humanLabel": ls.human_label,
                "acquiredAt": ls.acquired_at, "lastHeartbeat": ls.last_heartbeat}

    @app.post("/lease/acquire")
    def acquire_lease(actor: str = "human", mode: str = "edit",
                       baseRevision: int = -1, humanLabel: str = ""):
        if baseRevision < 0:
            baseRevision = get_current_revision(st.core)
        try:
            ls = get_lease_store(st.core).acquire(
                st.core.project.project_id,
                LeaseActor(actor), LeaseMode(mode), baseRevision, humanLabel)
            return {"ok": True, "sessionId": ls.session_id,
                    "actor": ls.actor.value, "mode": ls.mode.value,
                    "baseRevision": ls.base_revision}
        except LeaseConflictError as e:
            raise HTTPException(409, str(e))

    @app.post("/lease/release")
    def release_lease(sessionId: str):
        ok = get_lease_store(st.core).release(st.core.project.project_id, sessionId)
        return {"ok": ok}

    @app.post("/lease/heartbeat")
    def heartbeat_lease(sessionId: str):
        ok = get_lease_store(st.core).heartbeat(st.core.project.project_id, sessionId)
        return {"ok": ok}

    @app.post("/lease/handoff")
    def handoff_lease(fromSessionId: str, toActor: str = "agent",
                       toMode: str = "edit", toLabel: str = ""):
        try:
            ls = get_lease_store(st.core).handoff(
                st.core.project.project_id, fromSessionId,
                LeaseActor(toActor), LeaseMode(toMode), toLabel)
            return {"ok": True, "sessionId": ls.session_id,
                    "actor": ls.actor.value, "mode": ls.mode.value,
                    "humanLabel": ls.human_label}
        except (LeaseError, LeaseExpiredError) as e:
            raise HTTPException(409, str(e))

    @app.post("/mutation/check")
    def mutation_check(baseRevision: int, sessionId: str = ""):
        try:
            if sessionId:
                require_edit_right(st.core, sessionId)
            check_revision_match(st.core, baseRevision)
            return {"ok": True, "currentRevision": get_current_revision(st.core)}
        except (LeaseError, LeaseConflictError) as e:
            return {"ok": False, "error": str(e),
                    "currentRevision": get_current_revision(st.core)}

'''
    content = content.replace(marker, lease_endpoints + '\n' + marker, 1)
    print('2: endpoints added')

# Wrap POST /clips
old = '    @app.post("/clips")\n    def add_clip(req: AddClipReq):\n        return guard(lambda: st.cmd.add_clip(**req.model_dump()))'
new = '    @app.post("/clips")\n    def add_clip(req: AddClipReq, sessionId: str = ""):\n        def _do():\n            if sessionId:\n                require_edit_right(st.core, sessionId)\n            return st.cmd.add_clip(**req.model_dump())\n        return guard(_do)'
if old in content:
    content = content.replace(old, new, 1)
    print('3: /clips wrapped')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
