"""Theme / palette remapping for Excalidraw diagrams (v2 2.6).

Applies one of the alternative palettes documented in color-palette.md by
remapping each element's strokeColor and backgroundColor from the project's
"default" palette into the chosen target palette. Matching is best-effort via
nearest-neighbour in RGB space.
"""

from __future__ import annotations

from typing import Iterable

# Palette definitions mirror color-palette.md. Each palette maps a semantic
# role to (stroke, fill) colors; roles intentionally parallel across palettes
# so we can map by role.
PALETTES: dict[str, dict[str, tuple[str, str]]] = {
    "default": {
        "primary":   ("#1e1e1e", "#ffffff"),
        "accent":    ("#1971c2", "#a5d8ff"),
        "success":   ("#2f9e44", "#b2f2bb"),
        "warning":   ("#f08c00", "#ffec99"),
        "danger":    ("#e03131", "#ffc9c9"),
        "muted":     ("#868e96", "#f1f3f5"),
    },
    "warm": {
        "primary":   ("#3b0d0d", "#fff5f5"),
        "accent":    ("#d9480f", "#ffd8a8"),
        "success":   ("#c2255c", "#ffc9c9"),
        "warning":   ("#e67700", "#ffe8cc"),
        "danger":    ("#c92a2a", "#ffa8a8"),
        "muted":     ("#b08968", "#f8ecd2"),
    },
    "cool": {
        "primary":   ("#0b2545", "#eef4ff"),
        "accent":    ("#1864ab", "#a5d8ff"),
        "success":   ("#2b8a3e", "#96f2d7"),
        "warning":   ("#5c940d", "#d8f5a2"),
        "danger":    ("#0c8599", "#99e9f2"),
        "muted":     ("#495057", "#e9ecef"),
    },
    "high-contrast": {
        "primary":   ("#000000", "#ffffff"),
        "accent":    ("#000080", "#ffff00"),
        "success":   ("#006400", "#ccffcc"),
        "warning":   ("#8b4500", "#ffd700"),
        "danger":    ("#8b0000", "#ffcccc"),
        "muted":     ("#000000", "#d3d3d3"),
    },
    "minimal": {
        "primary":   ("#212529", "#ffffff"),
        "accent":    ("#495057", "#f1f3f5"),
        "success":   ("#343a40", "#f8f9fa"),
        "warning":   ("#495057", "#e9ecef"),
        "danger":    ("#212529", "#dee2e6"),
        "muted":     ("#adb5bd", "#f8f9fa"),
    },
}

VALID_THEMES: tuple[str, ...] = tuple(PALETTES.keys())


def _hex_to_rgb(h: str) -> tuple[int, int, int] | None:
    s = (h or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def _colour_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _find_role(colour: str, default_palette: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """Return (role, channel) where channel is 'stroke' or 'fill'."""
    rgb = _hex_to_rgb(colour)
    if rgb is None:
        return None
    best: tuple[int, tuple[str, str]] | None = None
    for role, (stroke, fill) in default_palette.items():
        for ch, ref in (("stroke", stroke), ("fill", fill)):
            ref_rgb = _hex_to_rgb(ref)
            if ref_rgb is None:
                continue
            dist = _colour_distance(rgb, ref_rgb)
            if best is None or dist < best[0]:
                best = (dist, (role, ch))
    return best[1] if best is not None else None


def apply_theme(data: dict, theme: str) -> dict:
    """Remap strokeColor/backgroundColor to match ``theme``. Mutates ``data``."""
    if theme not in PALETTES:
        raise ValueError(f"Unknown theme '{theme}'. Valid: {sorted(PALETTES.keys())}")
    if theme == "default":
        return data

    default = PALETTES["default"]
    target = PALETTES[theme]

    elements = data.get("elements") or []
    for el in elements:
        if not isinstance(el, dict):
            continue
        stroke = el.get("strokeColor")
        if isinstance(stroke, str) and stroke.lower() not in ("transparent", ""):
            hit = _find_role(stroke, default)
            if hit:
                role, _ = hit
                el["strokeColor"] = target[role][0]
        fill = el.get("backgroundColor")
        if isinstance(fill, str) and fill.lower() not in ("transparent", ""):
            hit = _find_role(fill, default)
            if hit:
                role, _ = hit
                el["backgroundColor"] = target[role][1]
    return data


def list_themes() -> Iterable[str]:
    return PALETTES.keys()
