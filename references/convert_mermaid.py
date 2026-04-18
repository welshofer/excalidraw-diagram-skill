"""Mermaid -> Excalidraw JSON converter (v2 2.7).

Supports a narrow subset: `graph TD` / `graph LR` with node definitions
(``A[Label]``) and edges (``A --> B``). Nodes become rectangles with visible
bound text and positions are laid out via a simple topological sort.

Usage:
    python convert_mermaid.py input.mmd -o out.excalidraw
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import defaultdict, deque
from pathlib import Path

from themes import PALETTES


_NODE_PATTERN = re.compile(r"([A-Za-z0-9_]+)\s*(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\})?")
_EDGE_PATTERN = re.compile(
    r"([A-Za-z0-9_]+)\s*(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\})?\s*"
    r"-->\s*"
    r"([A-Za-z0-9_]+)\s*(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\})?"
)


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def parse_mermaid(text: str) -> tuple[str, dict[str, str], list[tuple[str, str]]]:
    """Parse Mermaid source. Returns (direction, node_labels, edges)."""
    direction = "LR"
    labels: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue
        if line.startswith("graph "):
            parts = line.split()
            if len(parts) >= 2:
                direction = parts[1].upper()
            continue
        # Edge?
        m = _EDGE_PATTERN.search(line)
        if m:
            src = m.group(1)
            src_label = next((m.group(i) for i in (2, 3, 4) if m.group(i)), src)
            dst = m.group(5)
            dst_label = next((m.group(i) for i in (6, 7, 8) if m.group(i)), dst)
            labels.setdefault(src, src_label or src)
            labels.setdefault(dst, dst_label or dst)
            edges.append((src, dst))
            continue
        # Standalone node definition.
        m = _NODE_PATTERN.match(line)
        if m and m.group(1):
            node_id = m.group(1)
            label = next((m.group(i) for i in (2, 3, 4) if m.group(i)), node_id)
            labels.setdefault(node_id, label or node_id)
    return direction, labels, edges


def _topological_layers(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Return nodes grouped by topological depth (Kahn)."""
    indeg: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        indeg[b] += 1
    for n in nodes:
        indeg.setdefault(n, 0)
    layers: list[list[str]] = []
    layer = [n for n in nodes if indeg[n] == 0]
    visited: set[str] = set()
    while layer:
        layers.append(layer)
        visited.update(layer)
        next_layer: list[str] = []
        for n in layer:
            for m in adj.get(n, []):
                indeg[m] -= 1
                if indeg[m] == 0 and m not in visited:
                    next_layer.append(m)
        layer = next_layer
    # Remaining (cycles) get dumped into one final layer.
    remaining = [n for n in nodes if n not in visited]
    if remaining:
        layers.append(remaining)
    return layers


def compile_mermaid(text: str) -> dict:
    direction, labels, edges = parse_mermaid(text)
    nodes = list(labels.keys()) or list({n for e in edges for n in e})
    layers = _topological_layers(nodes, edges)

    node_w, node_h = 160, 60
    gap_x, gap_y = 60, 40
    positions: dict[str, tuple[float, float]] = {}
    for li, layer in enumerate(layers):
        for ni, node_id in enumerate(layer):
            if direction == "TD":
                x = ni * (node_w + gap_x) + 40
                y = li * (node_h + gap_y) + 40
            else:  # LR (default)
                x = li * (node_w + gap_x) + 40
                y = ni * (node_h + gap_y) + 40
            positions[node_id] = (x, y)

    stroke, fill = PALETTES["default"]["accent"]
    elements: list[dict] = []
    for node_id, (x, y) in positions.items():
        rid = _uid()
        tid = _uid()
        elements.append({
            "id": rid,
            "type": "rectangle",
            "x": x, "y": y, "width": node_w, "height": node_h,
            "strokeColor": stroke, "backgroundColor": fill,
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100, "seed": 1, "version": 1,
            "versionNonce": 1, "isDeleted": False,
            "boundElements": [{"id": tid, "type": "text"}],
            "updated": 1, "link": None, "locked": False,
            "_mermaid_id": node_id,
        })
        elements.append({
            "id": tid,
            "type": "text",
            "x": x + 8, "y": y + node_h / 2 - 10,
            "width": max(40, node_w - 16), "height": 20,
            "strokeColor": stroke, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100, "seed": 2, "version": 1,
            "versionNonce": 2, "isDeleted": False,
            "boundElements": None,
            "updated": 1, "link": None, "locked": False,
            "text": labels.get(node_id, node_id),
            "fontSize": 16, "fontFamily": 1,
            "textAlign": "center", "verticalAlign": "middle",
            "containerId": rid,
            "originalText": labels.get(node_id, node_id),
            "lineHeight": 1.25, "baseline": 14,
        })
    # Build a node_id -> rectangle element id map.
    node_rect: dict[str, str] = {}
    for el in elements:
        if "_mermaid_id" in el:
            node_rect[el["_mermaid_id"]] = el["id"]

    for src, dst in edges:
        rid = node_rect.get(src)
        did = node_rect.get(dst)
        if not rid or not did:
            continue
        sx, sy = positions[src]
        tx, ty = positions[dst]
        elements.append({
            "id": _uid(),
            "type": "arrow",
            "x": sx + node_w,
            "y": sy + node_h / 2,
            "width": max(1, tx - (sx + node_w)),
            "height": (ty + node_h / 2) - (sy + node_h / 2),
            "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": 1, "opacity": 100, "seed": 3, "version": 1,
            "versionNonce": 3, "isDeleted": False,
            "boundElements": None, "updated": 1, "link": None, "locked": False,
            "points": [[0, 0], [max(1, tx - (sx + node_w)), (ty + node_h / 2) - (sy + node_h / 2)]],
            "startBinding": {"elementId": rid, "focus": 0, "gap": 1},
            "endBinding": {"elementId": did, "focus": 0, "gap": 1},
            "startArrowhead": None, "endArrowhead": "arrow",
        })

    # Strip helper key.
    for el in elements:
        el.pop("_mermaid_id", None)

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "excalidraw-diagram-skill/mermaid",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Mermaid graph to Excalidraw JSON")
    parser.add_argument("input", type=str, help="Path to .mmd file or '-' for stdin")
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()
    if args.input == "-":
        text = sys.stdin.read()
    else:
        with open(args.input, "r", encoding="utf-8-sig") as f:
            text = f.read()
    data = compile_mermaid(text)
    payload = json.dumps(data, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
