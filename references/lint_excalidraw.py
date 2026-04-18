"""Lint Excalidraw diagrams for layout and design issues (2.4).

Usage:
    python lint_excalidraw.py <path-to-file.excalidraw>
    python lint_excalidraw.py --json <path-to-file.excalidraw>
    python lint_excalidraw.py --fix <path-to-file.excalidraw>

Checks performed:
  - Overlapping bounding boxes (elements stacked on top of each other)
  - Text overflow (text likely too wide for its container)
  - Identical coordinates (multiple elements at the exact same position)
  - Spacing consistency (uneven gaps between adjacent elements)
  - Unbound arrows (arrows not connected to any shape)
  - Tiny elements (shapes too small to be useful)

Auto-fix (--fix):
  - Widens containers to fit text content
  - Adjusts text position to center in container
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import from the render module for shared validation
sys.path.insert(0, str(Path(__file__).parent))
from render_excalidraw import validate_excalidraw, compute_bounding_box, logger, _ensure_main_handler


# ---------------------------------------------------------------------------
# Character width estimation per font family
# ---------------------------------------------------------------------------
# Average character width as a fraction of fontSize
CHAR_WIDTH_FACTORS = {
    1: 0.55,   # Virgil (hand-drawn) - wider
    2: 0.52,   # Helvetica (sans-serif)
    3: 0.60,   # Monospace (fixed-width) - widest
}
DEFAULT_CHAR_WIDTH_FACTOR = 0.55


def _estimate_text_width(text: str, font_size: float, font_family: int = 3) -> float:
    """Estimate the rendered width of text based on character count and font size."""
    factor = CHAR_WIDTH_FACTORS.get(font_family, DEFAULT_CHAR_WIDTH_FACTOR)
    # Use the longest line for multi-line text
    lines = text.split("\n") if text else [""]
    max_line_len = max(len(line) for line in lines)
    return max_line_len * font_size * factor


def _get_element_bbox(el: dict) -> tuple[float, float, float, float] | None:
    """Get (x, y, x2, y2) bounding box for an element, or None if not computable."""
    if not isinstance(el, dict):
        return None
    if el.get("isDeleted"):
        return None

    try:
        x = float(el.get("x", 0))
        y = float(el.get("y", 0))
        w = abs(float(el.get("width", 0)))
        h = abs(float(el.get("height", 0)))
    except (TypeError, ValueError):
        return None

    el_type = el.get("type", "")

    # For arrows/lines, use points array
    if el_type in ("arrow", "line") and "points" in el:
        points = el.get("points", [])
        if not points:
            return None
        min_x, min_y = x, y
        max_x, max_y = x, y
        for pt in points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    px = x + float(pt[0])
                    py = y + float(pt[1])
                    min_x = min(min_x, px)
                    min_y = min(min_y, py)
                    max_x = max(max_x, px)
                    max_y = max(max_y, py)
                except (TypeError, ValueError):
                    continue
        return (min_x, min_y, max_x, max_y)

    return (x, y, x + w, y + h)


def _boxes_overlap(a: tuple, b: tuple, threshold: float = 0.3) -> bool:
    """Check if two bounding boxes overlap significantly (more than threshold fraction)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix1 >= ix2 or iy1 >= iy2:
        return False

    intersection = (ix2 - ix1) * (iy2 - iy1)
    area_a = max((ax2 - ax1) * (ay2 - ay1), 1)
    area_b = max((bx2 - bx1) * (by2 - by1), 1)
    smaller_area = min(area_a, area_b)

    return intersection / smaller_area > threshold


def _check_frames(active: list[dict], id_map: dict, issues: list[dict]) -> None:
    """Run frame-specific lint checks (v2 2.5).

    - Frame-frame bounding box overlap (frames should not overlap each other).
    - Child elements (via containerId or boundElements) must lie within frame bounds.
    - Frame labels must fit within the frame's width.
    """
    frames = [e for e in active if e.get("type") == "frame"]
    if not frames:
        return

    # Frame-frame overlap.
    for i, a in enumerate(frames):
        bbox_a = _get_element_bbox(a)
        if bbox_a is None:
            continue
        for j, b in enumerate(frames):
            if i >= j:
                continue
            bbox_b = _get_element_bbox(b)
            if bbox_b is None:
                continue
            if _boxes_overlap(bbox_a, bbox_b, threshold=0.05):
                issues.append({
                    "severity": "warning",
                    "code": "frame-overlap",
                    "message": (
                        f"Frames '{a.get('id')}' and '{b.get('id')}' overlap. "
                        "Frames should be disjoint sections."
                    ),
                    "element_ids": [a.get("id"), b.get("id")],
                })

    # Child containment: elements referenced via boundElements or frameId.
    for frame in frames:
        fbbox = _get_element_bbox(frame)
        if fbbox is None:
            continue
        fx1, fy1, fx2, fy2 = fbbox
        child_ids: set[str] = set()
        bound = frame.get("boundElements") or []
        for be in bound:
            if isinstance(be, dict) and be.get("id"):
                child_ids.add(be["id"])
        # Elements might also mark their own frameId.
        for el in active:
            if el.get("frameId") == frame.get("id"):
                child_ids.add(el.get("id"))
        for cid in child_ids:
            child = id_map.get(cid)
            if not child:
                continue
            cbb = _get_element_bbox(child)
            if cbb is None:
                continue
            cx1, cy1, cx2, cy2 = cbb
            if cx1 < fx1 - 1 or cy1 < fy1 - 1 or cx2 > fx2 + 1 or cy2 > fy2 + 1:
                issues.append({
                    "severity": "warning",
                    "code": "frame-child-out-of-bounds",
                    "message": (
                        f"Element '{cid}' is a child of frame '{frame.get('id')}' "
                        "but its bounding box extends outside the frame."
                    ),
                    "element_ids": [cid, frame.get("id")],
                })

    # Frame label fits.
    for frame in frames:
        name = frame.get("name") or frame.get("label") or ""
        if not name:
            continue
        try:
            fw = abs(float(frame.get("width", 0)))
        except (TypeError, ValueError):
            fw = 0
        # Frame labels use a small pseudo font-size; estimate ~12px.
        est = _estimate_text_width(name, 14, 2)
        if fw and est > fw:
            issues.append({
                "severity": "info",
                "code": "frame-label-overflow",
                "message": (
                    f"Frame '{frame.get('id')}' label '{name[:40]}' "
                    f"(~{est:.0f}px) exceeds frame width ({fw:.0f}px)."
                ),
                "element_ids": [frame.get("id")],
            })


def lint_excalidraw(data: dict) -> list[dict]:
    """Lint an Excalidraw diagram for layout and design issues.

    Returns a list of issue dicts with keys:
      - severity: "error" | "warning" | "info"
      - code: short machine-readable code
      - message: human-readable description
      - element_ids: list of affected element IDs
      - fix: optional auto-fix suggestion
    """
    issues: list[dict] = []
    elements = data.get("elements", [])
    if not isinstance(elements, list):
        return issues

    active = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")]
    if not active:
        return issues

    id_map = {e["id"]: e for e in active if "id" in e}

    # --- Check 1: Overlapping bounding boxes ---
    # (v2 1.4) Sweep-line scan: O(n log n) on average instead of O(n^2).
    # (v2 1.6) Precompute each shape's bbox once, reused across comparisons.
    # (v2 2.5) Frames are handled separately by _check_frames() below; here we
    # skip non-frame overlap checks against frames but still inspect frame-frame
    # pairs inside _check_frames().
    shape_types = {"rectangle", "ellipse", "diamond", "frame"}
    non_frame_shapes = []
    for e in active:
        if e.get("type") in shape_types and e.get("type") != "frame":
            bbox = _get_element_bbox(e)
            if bbox is None:
                continue
            non_frame_shapes.append((e, bbox))

    # Sort by x1 (left edge).
    non_frame_shapes.sort(key=lambda t: t[1][0])

    # Active set indexed by index in the sorted list; we discard elements whose
    # x2 is already less than the current element's x1.
    active_list: list[tuple] = []
    seen_pairs: set[tuple] = set()
    for a, bbox_a in non_frame_shapes:
        ax1, _, ax2, _ = bbox_a
        # Evict from the active list any box whose x2 < current x1.
        active_list = [(b, bb) for (b, bb) in active_list if bb[2] >= ax1]
        a_bound = a.get("boundElements") or []
        a_bound_ids = {be.get("id") for be in a_bound if isinstance(be, dict)}
        for b, bbox_b in active_list:
            id_a = a.get("id")
            id_b = b.get("id")
            pair = (id_a, id_b) if (id_a or "") < (id_b or "") else (id_b, id_a)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            b_bound = b.get("boundElements") or []
            b_bound_ids = {be.get("id") for be in b_bound if isinstance(be, dict)}
            if id_b in a_bound_ids or id_a in b_bound_ids:
                continue
            if _boxes_overlap(bbox_a, bbox_b):
                issues.append({
                    "severity": "warning",
                    "code": "overlap",
                    "message": (
                        f"Elements '{id_a}' ({a.get('type')}) and "
                        f"'{id_b}' ({b.get('type')}) have significantly "
                        f"overlapping bounding boxes"
                    ),
                    "element_ids": [id_a, id_b],
                })
        active_list.append((a, bbox_a))

    # Restore a shapes list for later spacing/overlap sections.
    shapes = [e for e, _ in non_frame_shapes]

    # --- Frames-specific checks (v2 2.5) ---
    _check_frames(active, id_map, issues)

    # --- Check 2: Text overflow in containers ---
    for el in active:
        if el.get("type") != "text":
            continue
        container_id = el.get("containerId")
        if not container_id or container_id not in id_map:
            continue

        container = id_map[container_id]
        text = el.get("text", "") or el.get("originalText", "")
        font_size = el.get("fontSize", 16)
        font_family = el.get("fontFamily", 3)

        est_width = _estimate_text_width(text, font_size, font_family)
        container_w = abs(float(container.get("width", 0)))
        container_type = container.get("type", "rectangle")

        # Diamonds and ellipses have less usable internal width
        usable_factor = 1.0
        if container_type == "diamond":
            usable_factor = 0.55  # diamond inscribed rectangle
        elif container_type == "ellipse":
            usable_factor = 0.70  # ellipse inscribed rectangle

        usable_width = container_w * usable_factor
        # Add some padding
        usable_width -= 20

        if usable_width > 0 and est_width > usable_width:
            overflow_pct = ((est_width - usable_width) / usable_width) * 100
            issues.append({
                "severity": "warning",
                "code": "text-overflow",
                "message": (
                    f"Text in '{el.get('id')}' ('{text[:30]}...') likely overflows "
                    f"container '{container_id}' ({container_type}) by ~{overflow_pct:.0f}%. "
                    f"Estimated text width: {est_width:.0f}px, "
                    f"usable container width: {usable_width:.0f}px"
                ),
                "element_ids": [el.get("id"), container_id],
                "fix": {
                    "action": "widen_container",
                    "target": container_id,
                    "new_width": int(est_width / usable_factor + 40),
                },
            })

    # --- Check 3: Identical coordinates ---
    coord_map: dict[tuple, list[str]] = {}
    for el in active:
        if el.get("type") in ("text",) and el.get("containerId"):
            continue  # Skip bound text elements
        x = el.get("x")
        y = el.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            key = (round(float(x), 1), round(float(y), 1))
            coord_map.setdefault(key, []).append(el.get("id", "<unknown>"))

    for coord, ids in coord_map.items():
        if len(ids) > 1:
            # Filter out text labels that might legitimately share coordinates
            issues.append({
                "severity": "info",
                "code": "identical-coords",
                "message": (
                    f"Elements {ids} share identical coordinates ({coord[0]}, {coord[1]}). "
                    f"This may indicate copy-paste without repositioning."
                ),
                "element_ids": ids,
            })

    # --- Check 4: Spacing consistency ---
    # Check horizontal and vertical spacing between adjacent shapes
    if len(shapes) >= 3:
        # Sort shapes by x coordinate and check horizontal gaps
        sorted_by_x = sorted(shapes, key=lambda e: float(e.get("x", 0)))
        h_gaps = []
        for i in range(len(sorted_by_x) - 1):
            bbox_a = _get_element_bbox(sorted_by_x[i])
            bbox_b = _get_element_bbox(sorted_by_x[i + 1])
            if bbox_a and bbox_b:
                gap = bbox_b[0] - bbox_a[2]  # left of B - right of A
                if gap > 0:
                    h_gaps.append((gap, sorted_by_x[i].get("id"), sorted_by_x[i + 1].get("id")))

        if len(h_gaps) >= 2:
            gap_values = [g[0] for g in h_gaps]
            avg_gap = sum(gap_values) / len(gap_values)
            for gap_val, id_a, id_b in h_gaps:
                if avg_gap > 0 and abs(gap_val - avg_gap) / avg_gap > 0.5:
                    issues.append({
                        "severity": "info",
                        "code": "spacing-inconsistent",
                        "message": (
                            f"Horizontal gap between '{id_a}' and '{id_b}' "
                            f"({gap_val:.0f}px) differs significantly from "
                            f"average gap ({avg_gap:.0f}px)"
                        ),
                        "element_ids": [id_a, id_b],
                    })

    # --- Check 5: Unbound arrows ---
    for el in active:
        if el.get("type") != "arrow":
            continue
        start = el.get("startBinding")
        end = el.get("endBinding")
        if not start and not end:
            issues.append({
                "severity": "warning",
                "code": "unbound-arrow",
                "message": (
                    f"Arrow '{el.get('id')}' has no startBinding or endBinding. "
                    f"It is not connected to any shape."
                ),
                "element_ids": [el.get("id")],
            })

    # --- Check 6: Tiny elements ---
    for el in active:
        if el.get("type") in ("text", "arrow", "line"):
            continue
        w = abs(float(el.get("width", 0)))
        h = abs(float(el.get("height", 0)))
        if w < 15 and h < 15 and w > 0 and h > 0:
            # Skip marker dots (small ellipses are intentional)
            if el.get("type") == "ellipse" and w <= 15 and h <= 15:
                continue
            issues.append({
                "severity": "info",
                "code": "tiny-element",
                "message": (
                    f"Element '{el.get('id')}' ({el.get('type')}) is very small "
                    f"({w:.0f}x{h:.0f}px). This may be invisible or hard to see."
                ),
                "element_ids": [el.get("id")],
            })

    return issues


def auto_fix(data: dict, issues: list[dict]) -> dict:
    """Apply auto-fixes from lint issues. Returns modified data (2.4).

    Currently fixes:
    - text-overflow: widens the container to fit text
    """
    import copy
    fixed = copy.deepcopy(data)
    elements = fixed.get("elements", [])
    id_map = {e["id"]: e for e in elements if isinstance(e, dict) and "id" in e}

    fixes_applied = 0
    for issue in issues:
        fix_spec = issue.get("fix")
        if not fix_spec:
            continue

        if fix_spec.get("action") == "widen_container":
            target_id = fix_spec["target"]
            new_width = fix_spec["new_width"]
            if target_id in id_map:
                container = id_map[target_id]
                try:
                    old_width = float(container.get("width", 0))
                except (TypeError, ValueError):
                    old_width = 0.0
                try:
                    container_x = float(container.get("x", 0))
                except (TypeError, ValueError):
                    container_x = 0.0
                container["width"] = new_width
                # (v2 3.1) Correct re-centering math: explicitly place the text
                # so its center equals the new container center.
                new_container_center_x = container_x + new_width / 2
                for el in elements:
                    if isinstance(el, dict) and el.get("containerId") == target_id:
                        try:
                            ew = float(el.get("width", 0))
                        except (TypeError, ValueError):
                            ew = 0.0
                        # Grow text to fit (minus inset) when it was previously
                        # sized to the old container.
                        new_text_width = min(max(ew, new_width - 20), new_width - 20)
                        el["width"] = new_text_width
                        el["x"] = new_container_center_x - new_text_width / 2
                fixes_applied += 1
                logger.info(
                    f"Fixed: widened '{target_id}' from {old_width} to {new_width}px"
                )

    if fixes_applied:
        logger.info(f"Applied {fixes_applied} auto-fix(es)")
    return fixed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lint Excalidraw diagrams for layout and design issues (2.4)",
    )
    parser.add_argument("input", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument(
        "--fix", action="store_true",
        help="Auto-fix issues where possible (writes changes back to file)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")
    parser.add_argument(
        "--stats", action="store_true",
        help="Print diagram metrics instead of lint output (v2 2.8).",
    )
    args = parser.parse_args()

    if args.stats:
        # (v2 2.8) Delegate to render_excalidraw's stats printer.
        from render_excalidraw import _print_stats
        _print_stats(args.input, json_output=args.json_output)
        return

    if not args.input.exists():
        logger.error(f"File not found: {args.input}")
        sys.exit(1)

    # (v2 3.10) utf-8-sig tolerates BOM-prefixed files from Windows editors.
    raw = args.input.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        sys.exit(1)

    # Run structural validation first
    val_errors = validate_excalidraw(data)
    if val_errors:
        for err in val_errors:
            logger.error(f"  Validation: {err}")

    # Run lint checks
    issues = lint_excalidraw(data)

    if args.json_output:
        result = {
            "file": str(args.input),
            "validation_errors": val_errors,
            "lint_issues": issues,
            "counts": {
                "errors": sum(1 for i in issues if i["severity"] == "error"),
                "warnings": sum(1 for i in issues if i["severity"] == "warning"),
                "info": sum(1 for i in issues if i["severity"] == "info"),
            },
        }
        print(json.dumps(result, indent=2))
    else:
        # (v2 6.3) Always print a header with counts, then detail lines.
        errs = sum(1 for i in issues if i["severity"] == "error")
        warns = sum(1 for i in issues if i["severity"] == "warning")
        infos = sum(1 for i in issues if i["severity"] == "info")
        is_tty = sys.stdout.isatty()
        def _color(txt: str, code: str) -> str:
            return f"\033[{code}m{txt}\033[0m" if is_tty else txt
        summary = (
            f"Lint: {errs} errors, {warns} warnings, {infos} info, "
            f"{len(val_errors)} validation errors"
        )
        if errs or val_errors:
            print(_color(summary, "31"))  # red
        elif warns:
            print(_color(summary, "33"))  # yellow
        else:
            print(_color(summary, "32"))  # green
        if not issues and not val_errors:
            print(f"No issues found in {args.input.name}")
        else:
            for issue in issues:
                sev = issue["severity"].upper()
                print(f"  [{sev}] {issue['code']}: {issue['message']}")

    # Auto-fix mode
    if args.fix and any(i.get("fix") for i in issues):
        fixed_data = auto_fix(data, issues)
        args.input.write_text(
            json.dumps(fixed_data, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Fixes written to {args.input}")

    if any(i["severity"] == "error" for i in issues) or val_errors:
        sys.exit(1)


if __name__ == "__main__":
    _ensure_main_handler()
    main()
