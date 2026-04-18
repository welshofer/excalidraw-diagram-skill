"""Standalone Excalidraw JSON validation tool (no Playwright dependency).

Usage:
    python validate_excalidraw.py <path-to-file.excalidraw>
    python validate_excalidraw.py --json <path-to-file.excalidraw>

This script validates Excalidraw JSON files without requiring Playwright,
making it useful for quick validation checks during diagram development.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import validation functions from the render module
from render_excalidraw import (
    compute_bounding_box,
    validate_excalidraw,
    logger,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Excalidraw JSON files (no browser required)",
    )
    parser.add_argument("input", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")
    args = parser.parse_args()

    if not args.input.exists():
        logger.error(f"File not found: {args.input}")
        sys.exit(1)

    raw = args.input.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        if args.json_output:
            print(json.dumps({"valid": False, "errors": [f"Invalid JSON: {e}"]}))
        else:
            logger.error(f"Invalid JSON: {e}")
        sys.exit(1)

    errors = validate_excalidraw(data)

    if args.json_output:
        elements = data.get("elements", [])
        active = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")]
        bbox = compute_bounding_box(active) if active else (0, 0, 0, 0)
        result = {
            "valid": len(errors) == 0,
            "errors": errors,
            "elements": len(elements),
            "active_elements": len(active),
            "bounding_box": {
                "min_x": bbox[0], "min_y": bbox[1],
                "max_x": bbox[2], "max_y": bbox[3],
            },
        }
        print(json.dumps(result, indent=2))
    else:
        if errors:
            logger.error("Validation failed:")
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        else:
            elements = data.get("elements", [])
            active = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")]
            bbox = compute_bounding_box(active) if active else (0, 0, 0, 0)
            print(f"Valid Excalidraw file: {len(active)} active elements")
            if args.verbose:
                print(f"  Bounding box: ({bbox[0]:.0f}, {bbox[1]:.0f}) - ({bbox[2]:.0f}, {bbox[3]:.0f})")
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                print(f"  Diagram size: {w:.0f} x {h:.0f}")


if __name__ == "__main__":
    main()
