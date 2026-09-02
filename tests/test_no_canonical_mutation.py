"""GUI-04.5 P0-A regression guard: the canonical clean fixture
must never be mutated.

The fixture `projects/sanlihe-slice-30s-clean/` carries a
`CANONICAL_READONLY_DO_NOT_MUTATE` sentinel and is the source of
truth for UX-validation scenarios. Browser smoke scripts must
write to a working copy (`serve-clean-sanlihe.mjs` creates
`projects/_sanlihe-clean-work/`) — never the canonical itself.

If a smoke (or any other agent) mutates the canonical in place,
this test fails.

The guard compares the canonical `current.json` to the version
committed at HEAD. Any uncommitted change is a violation.

Why HEAD and not a recorded hash:
- HEAD tracks the truth.
- If a future batch legitimately updates the canonical (rebuilt
  via `scripts/build_clean_sanlihe_fixture.py` and committed),
  HEAD moves with it and the guard continues to enforce
  "canonical == HEAD".
- Stale on-disk canonical state vs HEAD is the only failure
  mode we care about.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CURRENT = ROOT / "projects" / "sanlihe-slice-30s-clean" / "current.json"
CANONICAL_SENTINEL = ROOT / "projects" / "sanlihe-slice-30s-clean" / "CANONICAL_READONLY_DO_NOT_MUTATE"


def _normalize_lf(data: bytes) -> bytes:
    """Normalize CRLF/CR to LF so the comparison is independent of
    the OS's git line-ending normalization (`core.autocrlf=true` on
    Windows converts LF→CRLF on checkout, which would otherwise make
    byte-level SHA comparison spuriously fail).

    The content under HEAD is LF (the canonical, deterministic form
    committed by every contributor). The on-disk form on Windows is
    CRLF. Both forms represent identical semantic content."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _sha256_lf(p: Path) -> str:
    return hashlib.sha256(_normalize_lf(p.read_bytes())).hexdigest()


def _sha256_lf_bytes(data: bytes) -> str:
    return hashlib.sha256(_normalize_lf(data)).hexdigest()


def _head_blob(relpath: str) -> bytes | None:
    """Return the bytes of `relpath` at HEAD, or None if absent."""
    res = subprocess.run(
        ["git", "show", f"HEAD:{relpath}"],
        cwd=ROOT,
        capture_output=True,
    )
    if res.returncode != 0:
        return None
    return res.stdout


def test_canonical_sentinel_present() -> None:
    """The sentinel file must exist; if it does not, someone
    deleted the protection flag."""
    assert CANONICAL_SENTINEL.exists(), (
        f"canonical sentinel missing: {CANONICAL_SENTINEL}. "
        "Restore it to mark this fixture as immutable."
    )


def test_canonical_current_matches_HEAD() -> None:
    """The canonical current.json on disk must be byte-identical
    to the version committed at HEAD. Any uncommitted mutation
    is a violation of the read-only contract.

    If this test fails after a deliberate canonical rebuild:
      1. Run `scripts/build_clean_sanlihe_fixture.py`
      2. Commit the new `current.json` (the sentinel should remain)
      3. Re-run pytest
    """
    assert CANONICAL_CURRENT.exists(), f"missing: {CANONICAL_CURRENT}"
    head_bytes = _head_blob("projects/sanlihe-slice-30s-clean/current.json")
    if head_bytes is None:
        # Canonical not yet committed — skip (first-time setup).
        pytest.skip("canonical not committed at HEAD yet")
    disk_hash = _sha256_lf(CANONICAL_CURRENT)
    head_hash = _sha256_lf_bytes(head_bytes)
    assert disk_hash == head_hash, (
        f"canonical current.json was mutated in place!\n"
        f"  on-disk SHA256: {disk_hash}\n"
        f"  HEAD SHA256:    {head_hash}\n"
        f"Smoke scripts must use the working copy "
        f"(`serve-clean-sanlihe.mjs`) instead of writing to the canonical."
    )


def test_canonical_sentinal_present():
    """Compat: typo'd name kept for grep resilience."""
    test_canonical_sentinel_present()


def test_working_copy_helper_exists() -> None:
    """The helper that creates a disposable working copy must exist
    and use a `_sanlihe-clean-work` path (the convention)."""
    helper = ROOT / "gui" / "smoke" / "serve-clean-sanlihe.mjs"
    assert helper.exists(), f"missing helper: {helper}"
    text = helper.read_text(encoding="utf-8")
    assert "_sanlihe-clean-work" in text, (
        f"helper {helper} does not reference the working-copy dir. "
        "It should always copy the canonical into a disposable location."
    )


@pytest.mark.parametrize("forbidden_dir", [
    "projects/_sanlihe-clean-work",
])
def test_canonical_is_not_a_working_copy(forbidden_dir: str) -> None:
    """Sanity: the canonical path itself must never BE the working
    copy. The working dir lives under `projects/` and starts with
    an underscore; the canonical does not."""
    canonical = ROOT / "projects" / "sanlihe-slice-30s-clean"
    work = ROOT / forbidden_dir
    assert canonical != work
    assert not canonical.name.startswith("_"), (
        f"canonical {canonical} should not be a hidden working dir"
    )


def test_no_canonical_mutation():
    """Aggregate: if the basic invariants above all pass, the
    canonical is intact. This test is the named entry point."""
    # Reuse the strongest check.
    test_canonical_current_matches_HEAD()
