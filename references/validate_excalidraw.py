"""Standalone Excalidraw JSON validation tool (no Playwright dependency).

Usage:
    python validate_excalidraw.py <path-to-file.excalidraw> [more.excalidraw ...]
    python validate_excalidraw.py --json <path-to-file.excalidraw>

(v2 1.9) Accepts multiple inputs so CI can validate a whole directory in a
single Python process rather than paying import cost per file.

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
    _ensure_main_handler,
)


def _validate_one(input_path: Path, *, json_output: bool, verbose: bool) -> tuple[bool, dict]:
    """Validate a single file. Returns (ok, result_dict)."""
    if not input_path.exists():
        return False, {
            "valid": False,
            "errors": [f"File not found: {input_path}"],
            "file": str(input_path),
        }

    # (v2 3.10) utf-8-sig tolerates BOM-prefixed files.
    try:
        raw = input_path.read_text(encoding="utf-8-sig")
    except OSError as e:
        return False, {
            "valid": False,
            "errors": [f"Cannot read {input_path}: {e}"],
            "file": str(input_path),
        }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, {"valid": False, "errors": [f"Invalid JSON: {e}"], "file": str(input_path)}

    errors = validate_excalidraw(data)
    elements = data.get("elements", [])
    active = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")]
    bbox = compute_bounding_box(active) if active else (0, 0, 0, 0)
    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "elements": len(elements),
        "active_elements": len(active),
        "file": str(input_path),
        "bounding_box": {
            "min_x": bbox[0],
            "min_y": bbox[1],
            "max_x": bbox[2],
            "max_y": bbox[3],
        },
    }
    return len(errors) == 0, result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Excalidraw JSON files (no browser required)",
    )
    parser.add_argument("input", type=Path, nargs="+", help="Path(s) to .excalidraw JSON file(s)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed info")
    args = parser.parse_args()

    all_ok = True
    results: list[dict] = []
    for input_path in args.input:
        ok, result = _validate_one(input_path, json_output=args.json_output, verbose=args.verbose)
        all_ok = all_ok and ok
        results.append(result)

    if args.json_output:
        if len(results) == 1:
            print(json.dumps(results[0], indent=2))
        else:
            print(
                json.dumps(
                    {
                        "valid": all_ok,
                        "count": len(results),
                        "results": results,
                    },
                    indent=2,
                )
            )
    else:
        for result in results:
            if result["valid"]:
                path = result["file"]
                print(
                    f"Valid Excalidraw file ({Path(path).name}): {result['active_elements']} active elements"
                )
                if args.verbose:
                    bbox = result["bounding_box"]
                    print(
                        f"  Bounding box: ({bbox['min_x']:.0f}, {bbox['min_y']:.0f}) - "
                        f"({bbox['max_x']:.0f}, {bbox['max_y']:.0f})"
                    )
                    w = bbox["max_x"] - bbox["min_x"]
                    h = bbox["max_y"] - bbox["min_y"]
                    print(f"  Diagram size: {w:.0f} x {h:.0f}")
            else:
                logger.error(f"Validation failed for {result['file']}:")
                for err in result["errors"]:
                    print(f"  - {err}", file=sys.stderr)

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    _ensure_main_handler()
    main()
