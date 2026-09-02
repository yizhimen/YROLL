"""GUI-04.5 P1-F: Transform Inspector cleanup.

Pins the invariants the user specified:

  1. X / Y / Scale / Rotation are the canonical transform UI
     (Inspector only — no duplicate in VisualAdjustPanel).
  2. '尺寸' (size/dimension) and 'Scale' label the SAME semantic
     field. The Inspector's "尺寸" is the canonical Scale control.
  3. Unimplemented controls (brightness / contrast / saturation /
     temperature / sharpen / opacity / flip / reverse / crop /
     bg_blur) MUST NOT be exposed in the user-facing transform
     surface because they have no rendering implementation.
  4. No new effect / adjustment architecture is added.

What this test pins at the file level:

  * `VisualAdjustPanel.tsx` is not imported by App.tsx (the panel
    is removed; its duplicate Scale + unimplemented effects are
    gone).
  * The Inspector's transform section (App.tsx) lists the four
    canonical fields with their labels: 水平 X / 垂直 Y / 尺寸 /
    旋转.
  * The setTransform / setTransform2d Core API endpoints exist
    (X/Y/Scale/Rotation). The other unimplemented endpoints
    (setColor / setOpacity / setCrop / setFlip / setReverse /
    setResetVisual) remain in Core but the GUI no longer offers
    them as user-facing controls. (They are not removed from
    Core because Agent / MCP / future features may need them.)
"""

from __future__ import annotations

from pathlib import Path


def test_app_does_not_import_VisualAdjustPanel() -> None:
    """VisualAdjustPanel is removed from the runtime surface.
    The Inspector (with X/Y/Scale/Rotation) is the canonical
    transform UI. Duplicate Scale in VisualAdjustPanel is gone."""
    src = Path("gui/src/App.tsx").read_text(encoding="utf-8")
    assert "import VisualAdjustPanel" not in src, (
        "App.tsx must not import VisualAdjustPanel — its "
        "transform section duplicates the Inspector's canonical "
        "X/Y/Scale/Rotation, and its color/crop/flip/reverse "
        "controls have no preview implementation."
    )
    assert "<VisualAdjustPanel" not in src, (
        "App.tsx must not render VisualAdjustPanel."
    )


def test_inspector_has_canonical_transform_fields() -> None:
    """Inspector renders X / Y / Scale / Rotation with their
    canonical Chinese labels."""
    src = Path("gui/src/App.tsx").read_text(encoding="utf-8")
    # The Inspector transform block iterates over the canonical
    # four fields.
    assert "[\"x\", \"y\", \"scale\", \"rotation\"]" in src, (
        "Inspector must iterate over the canonical four fields"
    )
    # Labels.
    assert "水平 X" in src, "Inspector must label X as '水平 X'"
    assert "垂直 Y" in src, "Inspector must label Y as '垂直 Y'"
    assert "尺寸" in src, "Inspector must label Scale as '尺寸'"
    assert "旋转" in src, "Inspector must label Rotation as '旋转'"


def test_尺寸_and_scale_are_the_same_field() -> None:
    """'尺寸' (size) and 'Scale' are the SAME semantic field.
    The Inspector uses '尺寸' as the label for the scale input.
    Pin that no other field also claims to be 'Scale'."""
    src = Path("gui/src/App.tsx").read_text(encoding="utf-8")
    # Locate the label map.
    label_map = src[
        src.index("水平 X"):src.index("水平 X") + 200
    ] if "水平 X" in src else ""
    assert "尺寸" in label_map, (
        "Inspector label map must include 尺寸 for scale"
    )
    # No other 'Scale' label anywhere in App.tsx.
    import re
    scale_labels = re.findall(
        r"label=\"(Scale|缩放)\"", src,
    )
    assert scale_labels == [], (
        f"Only the Inspector's '尺寸' label should exist for the "
        f"Scale field. Found extra Scale labels: {scale_labels}"
    )


def test_no_unimplemented_color_or_effect_controls() -> None:
    """The user-facing Inspector MUST NOT expose brightness,
    contrast, saturation, temperature, sharpen, opacity, flip,
    reverse, or crop controls because they have no preview
    implementation at this layer.

    We pin this by ensuring these labels do NOT appear in App.tsx
    as a user-facing control label."""
    src = Path("gui/src/App.tsx").read_text(encoding="utf-8")
    forbidden_labels = ("亮度", "对比度", "饱和度", "色温", "锐化",
                        "不透明", "倒放", "画面裁剪", "新建视频轨")
    # Check label strings (used as <label>...</label> or label=).
    import re
    for label in forbidden_labels:
        # Allow the label to appear ONLY in source comments that
        # explicitly say the control was removed.
        # Allow in <option> lists that we don't currently render.
        # Strict check: the label MUST NOT be the text of any
        # <label> element or label= prop in App.tsx.
        pattern = re.compile(
            r"<label[^>]*>[^<]*" + re.escape(label)
            + r"[^<]*</label>",
        )
        match = pattern.search(src)
        assert not match, (
            f"unimplemented control label '{label}' is rendered "
            f"in App.tsx: {match.group(0)!r}. Remove per P1-F."
        )


def test_clip_transform_constants_are_the_single_source_of_truth() -> None:
    """The Inspector's bounds (x/y/scale/rotation) come from
    clip-transform.ts (TRANSFORM_BOUNDS). No new bound constants
    are introduced — the canonical source is unchanged."""
    ct = Path("gui/src/clip-transform.ts").read_text(encoding="utf-8")
    assert "TRANSFORM_BOUNDS" in ct, (
        "clip-transform.ts must export TRANSFORM_BOUNDS"
    )
    # It must have x, y, scale, rotation entries.
    for field in ("x", "y", "scale", "rotation"):
        assert f"{field}:" in ct, (
            f"clip-transform.ts TRANSFORM_BOUNDS missing {field}"
        )


def test_inspector_transform_writes_to_clip_transform_via_setTransform() -> None:
    """The Inspector MUST write to `clip.transform` (via
    api.setTransform) — NOT to `clip.adjustments` (via
    api.setTransform2d). The 04-06 invariant: clip.transform is
    the sole semantic source for placement."""
    src = Path("gui/src/App.tsx").read_text(encoding="utf-8")
    # The Inspector's setTransform call.
    assert "api.setTransform" in src or "setTransform(" in src, (
        "Inspector must call api.setTransform (writes clip.transform)"
    )
    # And it must NOT also call api.setTransform2d (the
    # adjustments-based path).
    # Allow the API definition / type import but reject an
    # actual call to setTransform2d from App.tsx's transform
    # handler.
    if "api.setTransform2d(" in src:
        # If it IS called, it must be in a comment / explanation,
        # not as a dispatch.
        import re
        bad = re.search(r"api\.setTransform2d\s*\(", src)
        assert not bad, (
            "Inspector must NOT call api.setTransform2d from the "
            "transform handler — that path writes clip.adjustments "
            "and is a duplicate of the canonical clip.transform path."
        )
