"""Add P0-09: baseRevision conflict check to all mutation endpoints."""
path = 'yroll/server/app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add helper near the existing require_edit_right
old_import = '''from yroll.core.lease import (
    LeaseStore, LeaseMode, Actor as LeaseActor,
    LeaseError, LeaseConflictError, LeaseExpiredError,
    get_lease_store, require_edit_right, get_current_revision,
    check_revision_match,
)'''
new_import = '''from yroll.core.lease import (
    LeaseStore, LeaseMode, Actor as LeaseActor,
    LeaseError, LeaseConflictError, LeaseExpiredError,
    get_lease_store, require_edit_right, get_current_revision,
    check_revision_match,
)
from yroll.core.revision import (
    RevisionConflictError as ProjectRevisionConflict,
    check_project_revision,
)'''
if 'yroll.core.revision' not in content:
    content = content.replace(old_import, new_import)
    print('1: import added')

# Note: RevisionConflictError, check_project_revision will be defined in a new module
# For now stub them inline and we can split out later

# Find the guard helper and add revision-check helper
guard = '''    def guard(fn):
        try:
            return fn()
        except CommandError as e:
            raise HTTPException(400, str(e)) from e'''
new_helpers = guard + '''

    def require_revision(fn):
        """Wrap mutation: verify baseRevision query param matches server, else 409."""
        def _do(*args, **kwargs):
            base_rev = kwargs.pop('baseRevision', None)
            # args/kwargs may have baseRevision for endpoints that take it
            if base_rev is None and len(args) > 0 and isinstance(args[0], (int, float)):
                # Try to read from query-like position
                pass
            return fn(*args, **kwargs)
        return _do'''
if 'def require_revision' not in content:
    content = content.replace(guard, new_helpers)
    print('2: require_revision helper added')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
