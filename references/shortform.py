"""Compact shortform DSL that compiles to full Excalidraw JSON (v2 2.10).

Grammar (minimal, line-oriented):

    # comment lines start with '#'
    shape: rect id: a text: "Hello" at: [100, 100] size: [160, 80] role: primary
    shape: ellipse id: b text: "World" at: [300, 100] size: [120, 80]
    arrow: from: a to: b

Supported shapes: rect | ellipse | diamond | text | arrow | line
Supported roles: primary | accent | success | warning | danger | muted

Each non-arrow line produces one shape (+ its bound text when ``text`` is set).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from themes import PALETTES

_ROLES = ("primary", "accent", "success", "warning", "danger", "muted")
_SHAPE_ALIAS = {
    "rect": "rectangle",
    "rectangle": "rectangle",
    "ellipse": "ellipse",
    "oval": "ellipse",
    "diamond": "diamond",
    "text": "text",
}


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _parse_fields(line: str) -> dict[str, Any]:
    """Parse key: value pairs from a line.

    Values can be:
      - quoted strings: text: "Hello World"
      - bracketed lists: at: [100, 200]
      - bare tokens:    id: a
    """
    fields: dict[str, Any] = {}
    # Tokens: key:<space>value until the next key:
    pattern = re.compile(r"(\w+):\s*")
    positions = [(m.start(), m.end(), m.group(1)) for m in pattern.finditer(line)]
    for i, (start, value_start, key) in enumerate(positions):
        value_end = positions[i + 1][0] if i + 1 < len(positions) else len(line)
        value = line[value_start:value_end].strip().rstrip(",").strip()
        # Quoted string.
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            fields[key] = value[1:-1]
            continue
        # Bracketed list.
        if value.startswith("[") and value.endswith("]"):
            parts = [p.strip() for p in value[1:-1].split(",")]
            try:
                fields[key] = [float(p) if "." in p else int(p) for p in parts if p]
            except ValueError:
                fields[key] = parts
            continue
        fields[key] = value
    return fields


def _palette_colors(role: str) -> tuple[str, str]:
    palette = PALETTES["default"]
    stroke, fill = palette.get(role, palette["primary"])
    return stroke, fill


def _make_shape(fields: dict[str, Any]) -> list[dict]:
    shape_raw = str(fields.get("shape", "")).strip().lower()
    shape = _SHAPE_ALIAS.get(shape_raw, shape_raw)
    if not shape:
        raise ValueError("Missing 'shape:' field")
    sid = str(fields.get("id") or _uid())
    role = str(fields.get("role") or "primary").lower()
    if role not in _ROLES:
        role = "primary"
    stroke, fill = _palette_colors(role)
    x, y = 0, 0
    if isinstance(fields.get("at"), list) and len(fields["at"]) >= 2:
        x, y = fields["at"][0], fields["at"][1]
    w, h = 160, 80
    if isinstance(fields.get("size"), list) and len(fields["size"]) >= 2:
        w, h = fields["size"][0], fields["size"][1]
    base = {
        "id": sid,
        "type": shape,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": fill if shape != "text" else "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "seed": 1,
        "version": 1,
        "versionNonce": 1,
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }
    out = [base]
    text = fields.get("text")
    if text and shape != "text":
        tid = _uid()
        text_el = {
            "id": tid,
            "type": "text",
            "x": x + 10,
            "y": y + h / 2 - 10,
            "width": max(40, w - 20),
            "height": 20,
            "angle": 0,
            "strokeColor": stroke,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "seed": 2,
            "version": 1,
            "versionNonce": 2,
            "isDeleted": False,
            "boundElements": None,
            "updated": 1,
            "link": None,
            "locked": False,
            "text": str(text),
            "fontSize": 16,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": sid,
            "originalText": str(text),
            "lineHeight": 1.25,
            "baseline": 14,
        }
        base["boundElements"] = [{"id": tid, "type": "text"}]
        out.append(text_el)
    elif shape == "text":
        base["text"] = str(text or "")
        base["fontSize"] = 16
        base["fontFamily"] = 1
        base["textAlign"] = "left"
        base["verticalAlign"] = "top"
        base["lineHeight"] = 1.25
        base["baseline"] = 14
    return out


def _make_arrow(fields: dict[str, Any]) -> dict:
    src = str(fields.get("from", "")).strip()
    dst = str(fields.get("to", "")).strip()
    if not src or not dst:
        raise ValueError("arrow: requires from: and to:")
    return {
        "id": _uid(),
        "type": "arrow",
        "x": 0,
        "y": 0,
        "width": 100,
        "height": 0,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "seed": 3,
        "version": 1,
        "versionNonce": 3,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
        "points": [[0, 0], [100, 0]],
        "startBinding": {"elementId": src, "focus": 0, "gap": 1},
        "endBinding": {"elementId": dst, "focus": 0, "gap": 1},
        "startArrowhead": None,
        "endArrowhead": "arrow",
    }


def compile_shortform(raw: str) -> dict:
    """Compile shortform text to an Excalidraw JSON dict."""
    elements: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = _parse_fields(line)
        if "arrow" in fields or str(fields.get("shape", "")).lower() == "arrow":
            elements.append(_make_arrow(fields))
        else:
            elements.extend(_make_shape(fields))
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "excalidraw-diagram-skill/shortform",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Compile shortform DSL to Excalidraw JSON")
    parser.add_argument("input", type=str, help="Path to shortform file, or '-' for stdin")
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()
    if args.input == "-":
        text = sys.stdin.read()
    else:
        with open(args.input, "r", encoding="utf-8-sig") as f:
            text = f.read()
    data = compile_shortform(text)
    out = json.dumps(data, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        print(out)


if __name__ == "__main__":
    main()
