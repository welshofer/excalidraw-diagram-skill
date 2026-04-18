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
from render_excalidraw import validate_excalidraw, compute_bounding_box, logger


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
    shape_types = {"rectangle", "ellipse", "diamond", "frame"}
    shapes = [e for e in active if e.get("type") in shape_types]
    checked_pairs = set()

    for i, a in enumerate(shapes):
        bbox_a = _get_element_bbox(a)
        if bbox_a is None:
            continue
        for j, b in enumerate(shapes):
            if i >= j:
                continue
            pair_key = (a.get("id"), b.get("id"))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            bbox_b = _get_element_bbox(b)
            if bbox_b is None:
                continue

            # Skip container-text pairs (text inside shape is expected)
            a_bound = a.get("boundElements") or []
            b_bound = b.get("boundElements") or []
            a_bound_ids = {be.get("id") for be in a_bound if isinstance(be, dict)}
            b_bound_ids = {be.get("id") for be in b_bound if isinstance(be, dict)}
            if b.get("id") in a_bound_ids or a.get("id") in b_bound_ids:
                continue

            # Skip if one is a frame containing the other
            if a.get("type") == "frame" or b.get("type") == "frame":
                continue

            if _boxes_overlap(bbox_a, bbox_b):
                issues.append({
                    "severity": "warning",
                    "code": "overlap",
                    "message": (
                        f"Elements '{a.get('id')}' ({a.get('type')}) and "
                        f"'{b.get('id')}' ({b.get('type')}) have significantly "
                        f"overlapping bounding boxes"
                    ),
                    "element_ids": [a.get("id"), b.get("id")],
                })

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
                old_width = container.get("width", 0)
                container["width"] = new_width
                # Re-center bound text elements
                for el in elements:
                    if isinstance(el, dict) and el.get("containerId") == target_id:
                        delta = (new_width - old_width) / 2
                        el["x"] = el.get("x", 0) + delta / 2
                        el["width"] = el.get("width", 0) + delta
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
    args = parser.parse_args()

    if not args.input.exists():
        logger.error(f"File not found: {args.input}")
        sys.exit(1)

    raw = args.input.read_text(encoding="utf-8")
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
    main()
