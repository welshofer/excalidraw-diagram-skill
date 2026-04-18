"""Render Excalidraw JSON to PNG/SVG using Playwright + headless Chromium.

Usage:
    cd .claude/skills/excalidraw-diagram/references
    uv run python render_excalidraw.py <path-to-file.excalidraw> [--output path.png] [--scale 2] [--width 1920]

First-time setup:
    cd .claude/skills/excalidraw-diagram/references
    uv sync
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup (4.3)
# (v2 4.5) Only attach a StreamHandler when run as __main__. In library use
# we add a NullHandler so other loggers don't get double-logged.
# ---------------------------------------------------------------------------
logger = logging.getLogger("excalidraw_render")
logger.setLevel(logging.INFO)


def _ensure_main_handler() -> None:
    """Attach a stderr StreamHandler iff the module is run as a script (v2 4.5)."""
    for h in logger.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler):
            return
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(h)


if __name__ == "__main__":
    _ensure_main_handler()
else:
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_SAFE_INTEGER = 2**53 - 1
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB (3.6)
DEFAULT_MAX_ELEMENTS = 5000  # (5.6)
WARN_ELEMENTS = 2500
MAX_HEIGHT_DEFAULT = 10000  # (3.4)
EXCALIDRAW_VERSION = "0.18.0"  # Pinned version (1.2)
VENDOR_DIR = Path(__file__).parent / "vendor"  # (1.10) Local bundle directory
DANGEROUS_URL_SCHEMES = ("javascript:", "data:", "vbscript:")  # (5.5)
SYSTEM_DIRS = ("/etc", "/var", "/usr", "/System", "/Library")  # (5.3)

# Valid file extensions for input/output (5.3)
VALID_INPUT_EXTENSIONS = (".excalidraw", ".json")
VALID_OUTPUT_EXTENSIONS = (".png", ".svg", ".jpg", ".jpeg", ".html")

# Format presets (6.9)
FORMAT_PRESETS = {
    "presentation": {"width": 1920, "height": 1080, "scale": 2},
    "blog": {"width": 800, "height": 600, "scale": 2},
    "thumbnail": {"width": 400, "height": 300, "scale": 1},
    "social": {"width": 1200, "height": 630, "scale": 2},
}


class RenderError(Exception):
    """Raised when rendering fails."""


# (v2 2.2) Track auto-snapshotted previous PNGs keyed by output path string.
_LAST_PREV_SNAPSHOT: dict[str, Path] = {}


# ---------------------------------------------------------------------------
# Validation (2.2, 3.9, 4.5, 5.5, 5.6, 5.7)
# ---------------------------------------------------------------------------
def validate_excalidraw(data: dict, max_elements: int = DEFAULT_MAX_ELEMENTS) -> list[str]:
    """Validate Excalidraw JSON structure. Returns list of errors (empty = valid).

    Performs thorough validation including:
    - Top-level structure checks
    - Element-level required field checks
    - Cross-reference / binding integrity (4.5)
    - Duplicate ID detection (3.9)
    - Dangerous link URL detection (5.5)
    - Element count limits (5.6)
    - Seed value range checks (5.7)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("type") != "excalidraw":
        errors.append(
            f"Expected type 'excalidraw', got '{data.get('type')}'. "
            "Fix: Set the top-level 'type' field to 'excalidraw'."
        )

    if "elements" not in data:
        errors.append(
            "Missing 'elements' array. "
            "Fix: Your JSON needs an 'elements' key containing a list of diagram elements. "
            "See references/json-schema.md for the required structure."
        )
        return errors
    elif not isinstance(data["elements"], list):
        errors.append("'elements' must be an array")
        return errors
    elif len(data["elements"]) == 0:
        errors.append("'elements' array is empty -- nothing to render")
        return errors

    elements = data["elements"]

    # Element count check (5.6)
    if len(elements) > max_elements:
        errors.append(
            f"Element count ({len(elements)}) exceeds limit ({max_elements}). "
            f"Fix: Reduce element count or use --max-elements to increase the limit."
        )
    elif len(elements) > WARN_ELEMENTS:
        warnings.append(f"High element count ({len(elements)}). Rendering may be slow.")

    # Required fields per element type
    required_common = {"id", "type"}
    id_map: dict[str, dict] = {}
    duplicate_counts: dict[str, int] = {}
    # (v2 1.3) Consolidated two-pass validator. Pass 1 collects IDs, duplicates,
    # and per-element checks in a single walk. Pass 2 only does binding integrity.

    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            errors.append(f"Element at index {i} is not an object (got {type(el).__name__})")
            continue

        # (v2 6.5) Include JSONPath in errors that lack an id.
        raw_id = el.get("id")
        el_id = raw_id if raw_id is not None else f"<index:{i}>"
        el_path = f"$.elements[{i}]"
        el_type = el.get("type", "<missing>")

        # Check required common fields
        for field in required_common:
            if field not in el:
                errors.append(
                    f"Element '{el_id}' ({el_path}) missing required field '{field}'"
                )

        # Duplicate ID detection (3.9) -- in-stream, no separate pass.
        if "id" in el:
            if el["id"] in id_map:
                duplicate_counts[el["id"]] = duplicate_counts.get(el["id"], 1) + 1
            else:
                id_map[el["id"]] = el

        # Coordinate validation - warn on non-numeric
        for coord in ("x", "y"):
            val = el.get(coord)
            if val is not None and not isinstance(val, (int, float)):
                errors.append(
                    f"Element '{el_id}' ({el_path}) has non-numeric '{coord}': {val!r}. "
                    "Fix: Ensure x and y are numbers."
                )

        # Seed value validation (5.7, v2 5.8 rejects NaN/inf)
        import math as _math
        for seed_field in ("seed", "versionNonce"):
            val = el.get(seed_field)
            if val is not None:
                if isinstance(val, bool):
                    warnings.append(
                        f"Element '{el_id}' ({el_path}.{seed_field}) is a boolean: {val!r}"
                    )
                elif not isinstance(val, (int, float)):
                    warnings.append(
                        f"Element '{el_id}' ({el_path}.{seed_field}) non-numeric: {val!r}"
                    )
                elif isinstance(val, float) and (_math.isnan(val) or _math.isinf(val)):
                    errors.append(
                        f"Element '{el_id}' ({el_path}.{seed_field}) is NaN or infinity: {val}. "
                        "Fix: Use a finite integer."
                    )
                elif val < 0:
                    warnings.append(
                        f"Element '{el_id}' ({el_path}.{seed_field}) is negative: {val}"
                    )
                elif val > MAX_SAFE_INTEGER:
                    warnings.append(
                        f"Element '{el_id}' ({el_path}.{seed_field}) ({val}) exceeds "
                        f"JavaScript MAX_SAFE_INTEGER ({MAX_SAFE_INTEGER})"
                    )

        # Link URL validation (5.5, v2 5.9)
        link = el.get("link")
        if link and isinstance(link, str):
            link_stripped = link.strip()
            link_lower = link_stripped.lower()
            blocked = False
            for scheme in DANGEROUS_URL_SCHEMES:
                if link_lower.startswith(scheme):
                    errors.append(
                        f"Element '{el_id}' ({el_path}.link) has dangerous link URL scheme "
                        f"'{scheme}': {link[:80]}. "
                        "Fix: Only http:, https:, mailto:, or relative URLs are allowed."
                    )
                    blocked = True
                    break
            # (v2 5.9) Also block protocol-relative URLs (//evil.com) and UNC paths (\\).
            if not blocked and (link_stripped.startswith("//") or link_stripped.startswith("\\\\")):
                errors.append(
                    f"Element '{el_id}' ({el_path}.link) uses protocol-relative URL: "
                    f"{link[:80]}. "
                    "Fix: Use an explicit http:// or https:// prefix."
                )

        # Warn about zero-dimension elements (non-text, non-line/arrow)
        if el_type in ("rectangle", "ellipse", "diamond"):
            w = el.get("width", 0)
            h = el.get("height", 0)
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                if w == 0 and h == 0:
                    warnings.append(f"Element '{el_id}' ({el_type}) has zero width and height")

    # Report duplicate IDs
    for dup_id, count in duplicate_counts.items():
        errors.append(f"Duplicate element ID '{dup_id}' appears {count} times")

    # Binding integrity checks (4.5) -- second pass only.
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            continue
        el_id = el.get("id", f"<index:{i}>")
        el_path = f"$.elements[{i}]"

        # Check startBinding/endBinding references
        for binding_key in ("startBinding", "endBinding"):
            binding = el.get(binding_key)
            if binding and isinstance(binding, dict):
                ref_id = binding.get("elementId")
                if ref_id and ref_id not in id_map:
                    errors.append(
                        f"Element '{el_id}' ({el_path}.{binding_key}) references "
                        f"non-existent element '{ref_id}'"
                    )

        # Check containerId reference
        container_id = el.get("containerId")
        if container_id and container_id not in id_map:
            errors.append(
                f"Element '{el_id}' ({el_path}.containerId) references "
                f"non-existent element '{container_id}'"
            )

        # Bidirectional binding check: if text has containerId, container should list it
        if container_id and container_id in id_map:
            container = id_map[container_id]
            bound_els = container.get("boundElements") or []
            bound_ids = {b.get("id") for b in bound_els if isinstance(b, dict)}
            if el_id not in bound_ids and el.get("id") in id_map:
                warnings.append(
                    f"Element '{el_id}' has containerId='{container_id}' but "
                    f"container's boundElements does not include '{el_id}'"
                )

        # Check boundElements references
        bound_els = el.get("boundElements") or []
        if isinstance(bound_els, list):
            for bound in bound_els:
                if isinstance(bound, dict):
                    bound_id = bound.get("id")
                    if bound_id and bound_id not in id_map:
                        warnings.append(
                            f"Element '{el_id}' has boundElements entry "
                            f"referencing non-existent element '{bound_id}'"
                        )

    # Log warnings
    for w in warnings:
        logger.warning(w)

    return errors


# ---------------------------------------------------------------------------
# Bounding box computation (3.1, 3.2)
# ---------------------------------------------------------------------------
def compute_bounding_box(elements: list[dict]) -> tuple[float, float, float, float]:
    """Compute bounding box (min_x, min_y, max_x, max_y) across all elements.

    Handles malformed points (3.1) and non-numeric coordinates (3.2) gracefully.
    """
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        if not isinstance(el, dict):
            continue
        if el.get("isDeleted"):
            continue

        el_id = el.get("id", "<unknown>")

        # Safe numeric coercion (3.2)
        try:
            x = float(el.get("x", 0))
        except (TypeError, ValueError):
            logger.warning(f"Element '{el_id}' has non-numeric 'x': {el.get('x')!r}, defaulting to 0")
            x = 0.0
        try:
            y = float(el.get("y", 0))
        except (TypeError, ValueError):
            logger.warning(f"Element '{el_id}' has non-numeric 'y': {el.get('y')!r}, defaulting to 0")
            y = 0.0
        try:
            w = float(el.get("width", 0))
        except (TypeError, ValueError):
            logger.warning(f"Element '{el_id}' has non-numeric 'width': {el.get('width')!r}, defaulting to 0")
            w = 0.0
        try:
            h = float(el.get("height", 0))
        except (TypeError, ValueError):
            logger.warning(f"Element '{el_id}' has non-numeric 'height': {el.get('height')!r}, defaulting to 0")
            h = 0.0

        # For arrows/lines, points array defines the shape relative to x,y
        if el.get("type") in ("arrow", "line") and "points" in el:
            points = el["points"]
            if isinstance(points, list):
                for pt in points:
                    # Handle malformed points (3.1)
                    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                        logger.warning(
                            f"Element '{el_id}' has malformed point: {pt!r}, skipping"
                        )
                        continue
                    try:
                        px = float(pt[0])
                        py = float(pt[1])
                    except (TypeError, ValueError):
                        logger.warning(
                            f"Element '{el_id}' has non-numeric point values: {pt!r}, skipping"
                        )
                        continue
                    min_x = min(min_x, x + px)
                    min_y = min(min_y, y + py)
                    max_x = max(max_x, x + px)
                    max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))

    if min_x == float("inf"):
        return (0, 0, 800, 600)

    return (min_x, min_y, max_x, max_y)


# ---------------------------------------------------------------------------
# Path validation (5.3)
# ---------------------------------------------------------------------------
def validate_path(path: Path, kind: str = "input") -> list[str]:
    """Validate file paths to prevent path traversal and unsafe writes.

    (v2 3.8) Catches symlink loops (OSError ELOOP) when resolving.
    """
    errors: list[str] = []
    raw_str = str(path)
    try:
        resolved_str = str(path.resolve())
    except OSError as e:
        errors.append(
            f"Could not resolve path {raw_str!r}: {e}. "
            "Fix: Ensure the path does not contain a symlink cycle."
        )
        return errors

    if kind == "output":
        suffix = path.suffix.lower()
        if suffix not in VALID_OUTPUT_EXTENSIONS:
            errors.append(
                f"Output file must have one of {VALID_OUTPUT_EXTENSIONS} extension, "
                f"got '{suffix}'"
            )
        for sys_dir in SYSTEM_DIRS:
            # Check both raw and resolved paths (macOS resolves /etc -> /private/etc)
            if raw_str.startswith(sys_dir) or resolved_str.startswith(sys_dir):
                errors.append(
                    f"Refusing to write to system directory: {raw_str}. "
                    f"Fix: Use a path in your project directory."
                )
                break

    return errors


# ---------------------------------------------------------------------------
# Render caching (4.6)
# ---------------------------------------------------------------------------
def _get_cache_hash_path(excalidraw_path: Path) -> Path:
    """Return the path to the cache hash file for an excalidraw file."""
    return excalidraw_path.with_suffix(".excalidraw.hash")


def _check_cache(excalidraw_path: Path, output_path: Path, raw: str) -> bool:
    """Check if the render cache is still valid. Returns True if cached PNG is up-to-date."""
    hash_path = _get_cache_hash_path(excalidraw_path)
    if not hash_path.exists() or not output_path.exists():
        return False
    try:
        stored_hash = hash_path.read_text(encoding="utf-8").strip()
        current_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return stored_hash == current_hash
    except OSError:
        return False


def _write_cache(excalidraw_path: Path, raw: str) -> None:
    """Write the cache hash file."""
    hash_path = _get_cache_hash_path(excalidraw_path)
    try:
        current_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
        hash_path.write_text(current_hash, encoding="utf-8")
    except OSError:
        pass  # Cache write failure is non-fatal


# ---------------------------------------------------------------------------
# Vendor bundle detection (1.10) and integrity verification (5.10)
# ---------------------------------------------------------------------------
# (v2 1.2) Module-level caches keyed by (bundle mtime, integrity mtime, VENDOR_DIR id).
_VENDOR_AVAILABLE_CACHE: tuple[tuple, bool] | None = None
_RESOLVED_TEMPLATE_CACHE: tuple[tuple, str] | None = None


def _vendor_cache_key() -> tuple:
    """Build a cache key for vendor detection and template resolution (v2 1.2)."""
    bundle_path = VENDOR_DIR / "excalidraw-bundle.js"
    integrity_path = VENDOR_DIR / "integrity.json"
    template_path = Path(__file__).parent / "render_template.html"

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return -1.0

    return (
        str(VENDOR_DIR),
        _mtime(bundle_path),
        _mtime(integrity_path),
        _mtime(template_path),
    )


def _vendor_bundle_available() -> bool:
    """Check if a vendored Excalidraw bundle exists and passes integrity check.

    (v2 1.2) Memoized; invalidated when VENDOR_DIR or its file mtimes change.
    """
    global _VENDOR_AVAILABLE_CACHE
    key = _vendor_cache_key()
    if _VENDOR_AVAILABLE_CACHE is not None and _VENDOR_AVAILABLE_CACHE[0] == key:
        return _VENDOR_AVAILABLE_CACHE[1]

    bundle_path = VENDOR_DIR / "excalidraw-bundle.js"
    integrity_path = VENDOR_DIR / "integrity.json"
    if not bundle_path.exists() or not integrity_path.exists():
        _VENDOR_AVAILABLE_CACHE = (key, False)
        return False
    try:
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        content = bundle_path.read_bytes()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != integrity.get("sha256"):
            logger.warning("Vendor bundle integrity check failed -- falling back to CDN")
            _VENDOR_AVAILABLE_CACHE = (key, False)
            return False
        # (v2 4.7) Warn on version mismatch against the pinned constant.
        vendor_version = integrity.get("version")
        if vendor_version and vendor_version != EXCALIDRAW_VERSION:
            logger.warning(
                f"Vendor bundle version ({vendor_version}) differs from "
                f"EXCALIDRAW_VERSION ({EXCALIDRAW_VERSION}); re-run vendor_excalidraw.py."
            )
        _VENDOR_AVAILABLE_CACHE = (key, True)
        return True
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Cannot verify vendor bundle: {e}")
        _VENDOR_AVAILABLE_CACHE = (key, False)
        return False


def _invalidate_caches() -> None:
    """Reset module caches (used by tests that monkey-patch VENDOR_DIR) (v2 1.2)."""
    global _VENDOR_AVAILABLE_CACHE, _RESOLVED_TEMPLATE_CACHE
    _VENDOR_AVAILABLE_CACHE = None
    _RESOLVED_TEMPLATE_CACHE = None


def _get_vendor_sri() -> str | None:
    """Get the SRI hash for the vendored bundle (5.10)."""
    integrity_path = VENDOR_DIR / "integrity.json"
    try:
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        return integrity.get("sri")
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return None


def _resolve_template_html() -> str:
    """Load the render template, using vendored bundle if available (1.10, 5.10).

    If vendor/excalidraw-bundle.js exists and passes integrity check,
    the template is rewritten to inline the bundle via a blob: URL,
    eliminating the CDN dependency. An SRI-equivalent integrity check
    is performed at load time via the integrity.json sha256 verification.

    (v2 1.2) Memoized across calls keyed on (VENDOR_DIR, file mtimes).
    """
    global _RESOLVED_TEMPLATE_CACHE
    key = _vendor_cache_key()
    if _RESOLVED_TEMPLATE_CACHE is not None and _RESOLVED_TEMPLATE_CACHE[0] == key:
        return _RESOLVED_TEMPLATE_CACHE[1]

    template_path = Path(__file__).parent / "render_template.html"
    if not template_path.exists():
        raise RenderError(f"Template not found at {template_path}")
    template_html = template_path.read_text(encoding="utf-8")

    if _vendor_bundle_available():
        bundle_js = (VENDOR_DIR / "excalidraw-bundle.js").read_text(encoding="utf-8")
        # Replace the CDN import with an inline blob URL approach.
        # We wrap the vendor bundle in a blob and import from it.
        vendor_template = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <!-- (5.4, v2 5.1) CSP for local vendor bundle.
       Dropped 'unsafe-inline'; inline bootstrap scripts use a nonce +
       'strict-dynamic', and the vendor bundle is loaded from a blob: URL. -->
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src blob: 'strict-dynamic' 'nonce-exc-template'; style-src 'unsafe-inline'; img-src 'self' data:">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ overflow: hidden; }}
    #root {{ display: inline-block; }}
    #root svg {{ display: block; }}
  </style>
</head>
<body>
  <div id="root"></div>

  <script nonce="exc-template">
    // (1.10) Vendor bundle loaded locally -- no CDN dependency
    // (5.10) Integrity verified via sha256 at load time by render script
    const bundleCode = {json.dumps(bundle_js)};
    const blob = new Blob([bundleCode], {{ type: "text/javascript" }});
    const blobUrl = URL.createObjectURL(blob);

    import(blobUrl).then((mod) => {{
      window._excalidrawMod = mod;
      window.renderDiagram = async function(jsonData) {{
        try {{
          const data = typeof jsonData === "string" ? JSON.parse(jsonData) : jsonData;
          const elements = data.elements || [];
          const appState = data.appState || {{}};
          const files = data.files || {{}};
          const bgColor = appState.viewBackgroundColor || "#ffffff";
          document.body.style.background = bgColor;
          const darkMode = appState.exportWithDarkMode || false;
          const svg = await mod.exportToSvg({{
            elements: elements,
            appState: {{
              ...appState,
              viewBackgroundColor: bgColor,
              exportWithDarkMode: darkMode,
              exportBackground: true,
            }},
            files: files,
          }});
          const root = document.getElementById("root");
          root.innerHTML = "";
          root.appendChild(svg);
          // (v2 3.9) Success-only sets __renderComplete.
          window.__renderError = null;
          window.__renderComplete = true;
          return {{ success: true, width: svg.getAttribute("width"), height: svg.getAttribute("height") }};
        }} catch (err) {{
          window.__renderError = err.message || String(err);
          return {{ success: false, error: err.message || String(err) }};
        }}
      }};
      window.__moduleReady = true;
    }}).catch((err) => {{
      window.__moduleError = err.message || "Failed to load vendor bundle";
    }});
  </script>

  <script nonce="exc-template">
    window.addEventListener("error", function(e) {{
      window.__moduleError = e.message || "Unknown module load error";
    }});
  </script>
</body>
</html>"""
        logger.info("Using vendored Excalidraw bundle (offline mode)")
        _RESOLVED_TEMPLATE_CACHE = (key, vendor_template)
        return vendor_template

    _RESOLVED_TEMPLATE_CACHE = (key, template_html)
    return template_html


# ---------------------------------------------------------------------------
# Connectivity check (4.10)
# ---------------------------------------------------------------------------
def _check_connectivity(host: str = "esm.sh", timeout: float = 3.0, attempts: int = 2) -> bool:
    """Check DNS reachability for ``host`` with exponential backoff (v2 4.6)."""
    delays = [0.0, 1.0, 2.0]
    for attempt in range(max(1, attempts)):
        if attempt < len(delays) and delays[attempt]:
            time.sleep(delays[attempt])
        try:
            socket.setdefaulttimeout(timeout)
            socket.getaddrinfo(host, 443)
            return True
        except (socket.gaierror, socket.timeout, OSError):
            continue
    return False


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------
def render(
    excalidraw_path: Path,
    output_path: Path | None = None,
    scale: int = 2,
    max_width: int = 1920,
    max_height: int = MAX_HEIGHT_DEFAULT,
    timeout: int = 30,
    svg_output: bool = False,
    html_output: bool = False,
    dark_mode: bool = False,
    crop: tuple[int, int, int, int] | None = None,
    force: bool = False,
    max_elements: int = DEFAULT_MAX_ELEMENTS,
    json_output: bool = False,
    dry_run: bool = False,
    open_after: bool = False,
    *,
    watermark: bool = False,
    theme: str | None = None,
    html_inline: bool = False,
    pdf_output: bool = False,
) -> Path:
    """Render an .excalidraw file to PNG/SVG/HTML. Returns the output path.

    Raises RenderError on failure instead of calling sys.exit (3.5).
    """
    t_start = time.time()

    # Determine output suffix
    if svg_output:
        default_suffix = ".svg"
    elif html_output:
        default_suffix = ".html"
    elif pdf_output:
        default_suffix = ".pdf"
    else:
        default_suffix = ".png"

    # Validate file size (3.6)
    try:
        file_size = excalidraw_path.stat().st_size
    except OSError as e:
        raise RenderError(f"Cannot read file {excalidraw_path}: {e}")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise RenderError(
            f"File size ({file_size / 1024 / 1024:.1f} MB) exceeds limit "
            f"({MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB). "
            "Fix: Reduce diagram size or split into multiple files."
        )

    # Read and validate. (v2 3.10) utf-8-sig to tolerate BOM-prefixed files.
    logger.info(f"Reading {excalidraw_path}...")
    raw = excalidraw_path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RenderError(
            f"Invalid JSON in {excalidraw_path}: {e}. "
            "Fix: Check for trailing commas, missing quotes, or unescaped characters."
        )

    # (v2 2.6) Apply theme palette before validation so remapped fills are ok.
    if theme and theme != "default":
        try:
            from themes import apply_theme  # type: ignore
            apply_theme(data, theme)
        except ImportError:
            logger.warning("themes module not available; skipping --theme")

    errors = validate_excalidraw(data, max_elements=max_elements)
    if errors:
        msg = "Invalid Excalidraw file:\n" + "\n".join(f"  - {err}" for err in errors)
        raise RenderError(msg)

    # Compute viewport size from element bounding box
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    min_x, min_y, max_x, max_y = compute_bounding_box(elements)
    padding = 80
    diagram_w = max_x - min_x + padding * 2
    diagram_h = max_y - min_y + padding * 2

    # Cap viewport (1.4 - reduced minimum, 3.4 - max height cap)
    vp_width = min(int(diagram_w), max_width)
    vp_height = min(max(int(diagram_h), 100), max_height)

    # Auto-scale if diagram exceeds both caps (3.4)
    zoom = 1.0
    if diagram_w > max_width and diagram_h > max_height:
        zoom_w = max_width / diagram_w
        zoom_h = max_height / diagram_h
        zoom = min(zoom_w, zoom_h)
        logger.warning(
            f"Diagram ({int(diagram_w)}x{int(diagram_h)}) exceeds viewport caps "
            f"({max_width}x{max_height}). Auto-scaling to {zoom:.2f}x."
        )

    # Output path
    if output_path is None:
        output_path = excalidraw_path.with_suffix(default_suffix)

    # Dry-run mode (4.9): validate only, no browser
    if dry_run:
        result = {
            "success": True,
            "mode": "dry-run",
            "elements": len(elements),
            "viewport": {"width": vp_width, "height": vp_height},
            "bounding_box": {
                "min_x": min_x, "min_y": min_y,
                "max_x": max_x, "max_y": max_y,
            },
            "warnings": [],
        }
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            logger.info(f"Dry-run: {len(elements)} elements, viewport {vp_width}x{vp_height}")
            logger.info(f"Bounding box: ({min_x:.0f}, {min_y:.0f}) - ({max_x:.0f}, {max_y:.0f})")
        return output_path

    # Check cache (4.6)
    if not force and not svg_output and not html_output and _check_cache(excalidraw_path, output_path, raw):
        logger.info(f"Cache hit -- skipping render (use --force to override)")
        if json_output:
            print(json.dumps({"success": True, "output": str(output_path), "cached": True}))
        else:
            print(str(output_path))
        return output_path

    # HTML export (7.10) - no browser needed
    if html_output:
        _export_html(data, output_path, dark_mode, inline_bundle=html_inline)
        logger.info(f"HTML export saved to {output_path}")
        if open_after:
            _open_file(output_path)
        return output_path

    # (v2 2.2) Auto-snapshot previous render for diff support.
    prev_snapshot: Path | None = None
    if output_path.exists() and not svg_output and not pdf_output:
        prev_snapshot = output_path.with_suffix(output_path.suffix + ".prev")
        try:
            import shutil as _shutil
            _shutil.copy2(str(output_path), str(prev_snapshot))
            _LAST_PREV_SNAPSHOT[str(output_path)] = prev_snapshot
        except OSError:
            prev_snapshot = None

    # Import playwright here so validation errors show before import errors (1.8)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenderError(
            "playwright not installed. "
            "Fix: The render pipeline uses a headless browser. "
            "Run: cd references && uv sync && uv run playwright install chromium"
        )

    # (1.10) Use vendored bundle if available, otherwise check connectivity
    use_vendor = _vendor_bundle_available()
    if not use_vendor:
        # Connectivity check (4.10)
        if not _check_connectivity():
            raise RenderError(
                "Cannot reach esm.sh -- check internet connection. "
                "Fix: Ensure you have internet access, or run "
                "'python vendor_excalidraw.py' to download a local bundle."
            )

    # Template (5.9 - use set_content instead of file://)
    template_html = _resolve_template_html()

    # Apply dark mode to template if requested (2.3)
    if dark_mode:
        data.setdefault("appState", {})
        data["appState"]["exportWithDarkMode"] = True
        if "viewBackgroundColor" not in data.get("appState", {}):
            data["appState"]["viewBackgroundColor"] = "#1e1e1e"

    # Apply zoom for oversized diagrams (3.4)
    if zoom < 1.0:
        data.setdefault("appState", {})
        data["appState"]["zoom"] = zoom

    # Calculate timeouts (3.8)
    module_timeout = int(timeout * 1000 * 0.6)
    render_timeout = int(timeout * 1000 * 0.4)

    # Retry logic (4.7)
    last_error = None
    for attempt in range(3):
        if attempt > 0:
            logger.info(f"Retry attempt {attempt + 1}/3...")
            time.sleep(1)

        try:
            _render_with_playwright(
                sync_playwright,
                template_html,
                data,
                output_path,
                vp_width,
                vp_height,
                scale,
                module_timeout,
                render_timeout,
                svg_output,
                crop,
                pdf_output=pdf_output,
            )
            last_error = None
            break
        except RenderError:
            raise  # Don't retry on validation / known errors
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Only retry on transient errors
            if any(kw in error_str for kw in ("timeout", "crash", "target closed", "connection refused")):
                logger.warning(f"Transient error on attempt {attempt + 1}: {e}")
                continue
            raise RenderError(f"Render failed: {e}")

    if last_error is not None:
        raise RenderError(f"Render failed after 3 attempts: {last_error}")

    t_elapsed = time.time() - t_start

    # (v2 2.1) Apply watermark to PNG outputs.
    if watermark and not svg_output and not pdf_output:
        _apply_watermark(output_path)

    # Write cache (4.6)
    if not svg_output and not pdf_output:
        _write_cache(excalidraw_path, raw)

    # JSON output mode (4.4)
    if json_output:
        result = {
            "success": True,
            "output": str(output_path),
            "viewport": {"width": vp_width, "height": vp_height},
            "elements": len(elements),
            "elapsed_seconds": round(t_elapsed, 2),
            "warnings": [],
        }
        print(json.dumps(result, indent=2))
    else:
        print(str(output_path))

    # Open after render (6.1)
    if open_after:
        _open_file(output_path)

    return output_path


def _render_with_playwright(
    sync_playwright,
    template_html: str,
    data: dict,
    output_path: Path,
    vp_width: int,
    vp_height: int,
    scale: int,
    module_timeout: int,
    render_timeout: int,
    svg_output: bool,
    crop: tuple[int, int, int, int] | None,
    pdf_output: bool = False,
) -> None:
    """Internal render using Playwright. Uses try/finally for cleanup (3.5)."""
    with sync_playwright() as p:
        browser = None
        try:
            logger.info("Launching browser...")
            # (5.2) Launch with restrictive args
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage"],
            )
            # (v2 3.7) Confirm the launched browser is actually alive.
            try:
                _ = browser.version
            except Exception:
                raise RenderError(
                    "Chromium failed to start. "
                    "Fix: run `uv run playwright install chromium --with-deps`."
                )

            # (5.2) Restrict permissions
            context = browser.new_context(
                viewport={"width": vp_width, "height": vp_height},
                device_scale_factor=scale,
                permissions=[],
            )
            page = context.new_page()

            # (5.9) Load template via set_content instead of file:// for security
            logger.info("Loading Excalidraw library...")
            page.set_content(template_html)

            # Wait for the ES module to load
            try:
                page.wait_for_function("window.__moduleReady === true", timeout=module_timeout)
            except Exception as e:
                if "timeout" in str(e).lower():
                    raise RenderError(
                        "Failed to load Excalidraw library from esm.sh -- check internet connection. "
                        "The module load timed out after "
                        f"{module_timeout / 1000:.0f}s."
                    )
                raise

            # (5.1, 3.7) Pass data as argument instead of string interpolation
            logger.info(f"Rendering diagram ({len(data.get('elements', []))} elements)...")
            result = page.evaluate("(data) => window.renderDiagram(data)", data)

            if not result or not result.get("success"):
                error_msg = result.get("error", "Unknown render error") if result else "renderDiagram returned null"
                raise RenderError(f"Render failed: {error_msg}")

            # Wait for render completion signal
            try:
                page.wait_for_function("window.__renderComplete === true", timeout=render_timeout)
            except Exception as e:
                if "timeout" in str(e).lower():
                    raise RenderError(
                        f"Render completion timed out after {render_timeout / 1000:.0f}s. "
                        "Fix: Try --timeout with a larger value for complex diagrams."
                    )
                raise

            # (1.9) Check actual SVG dimensions and resize viewport if needed
            svg_dims = page.evaluate("""() => {
                const svg = document.querySelector('#root svg');
                if (!svg) return null;
                return {
                    width: parseInt(svg.getAttribute('width') || '0'),
                    height: parseInt(svg.getAttribute('height') || '0')
                };
            }""")

            if svg_dims:
                actual_w = svg_dims.get("width", 0)
                actual_h = svg_dims.get("height", 0)
                if actual_w > vp_width or actual_h > vp_height:
                    new_w = max(vp_width, actual_w + 20)
                    new_h = max(vp_height, actual_h + 20)
                    logger.info(
                        f"SVG dimensions ({actual_w}x{actual_h}) exceed viewport "
                        f"({vp_width}x{vp_height}). Resizing to {new_w}x{new_h}."
                    )
                    page.set_viewport_size({"width": new_w, "height": new_h})

            if svg_output:
                # (1.5) SVG output - extract SVG HTML directly
                logger.info("Extracting SVG...")
                svg_html = page.evaluate("""() => {
                    const svg = document.querySelector('#root svg');
                    return svg ? svg.outerHTML : null;
                }""")
                if svg_html is None:
                    raise RenderError("No SVG element found after render.")
                output_path.write_text(svg_html, encoding="utf-8")
            elif pdf_output:
                # (v2 2.9) PDF output via Chromium CDP. Playwright's page.pdf()
                # only runs in headless mode with the default browser type.
                logger.info("Rendering PDF...")
                # Compute PDF page size from SVG bounds so content fits.
                pdf_size = page.evaluate("""() => {
                    const svg = document.querySelector('#root svg');
                    if (!svg) return null;
                    return {
                        width: parseInt(svg.getAttribute('width') || '800'),
                        height: parseInt(svg.getAttribute('height') || '600')
                    };
                }""")
                pw_ = (pdf_size or {}).get("width") or 800
                ph_ = (pdf_size or {}).get("height") or 600
                try:
                    page.pdf(
                        path=str(output_path),
                        width=f"{pw_ + 20}px",
                        height=f"{ph_ + 20}px",
                        print_background=True,
                    )
                except Exception as e:
                    raise RenderError(
                        f"PDF export failed: {e}. "
                        "PDF export requires Playwright headless Chromium."
                    )
            else:
                # Screenshot the SVG element
                svg_el = page.query_selector("#root svg")
                if svg_el is None:
                    raise RenderError("No SVG element found after render.")

                # (1.6) Crop support
                if crop:
                    cx, cy, cw, ch = crop
                    logger.info(f"Cropping to region ({cx}, {cy}, {cw}, {ch})")
                    page.screenshot(
                        path=str(output_path),
                        clip={"x": cx, "y": cy, "width": cw, "height": ch},
                    )
                else:
                    svg_el.screenshot(path=str(output_path))

            logger.info(f"Saved to {output_path}")

        except RenderError:
            raise
        except Exception as e:
            raise RenderError(f"Browser error: {e}")
        finally:
            # (3.5) Always close browser
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# HTML export (7.10)
# ---------------------------------------------------------------------------
def _export_html(data: dict, output_path: Path, dark_mode: bool = False, inline_bundle: bool = False) -> None:
    """Export diagram as self-contained interactive HTML file.

    (v2 2.3) When the vendor bundle is available (or --html-inline is set), inline
    the JS bundle via a blob URL so the export works offline/air-gapped.
    (v2 5.7) Escape '</' inside the embedded JSON to prevent early script
    termination when user-supplied text contains '</script>' etc.
    """
    json_str = json.dumps(data).replace("</", "<\\/")
    bg_color = "#1e1e1e" if dark_mode else "#ffffff"

    use_vendor = inline_bundle or _vendor_bundle_available()
    if use_vendor and (VENDOR_DIR / "excalidraw-bundle.js").exists():
        bundle_js = (VENDOR_DIR / "excalidraw-bundle.js").read_text(encoding="utf-8")
        vendor_js_literal = json.dumps(bundle_js)
        # Blob-URL pattern: no CDN, no external fetch.
        script_block = f"""<script>
    const bundleCode = {vendor_js_literal};
    const blob = new Blob([bundleCode], {{ type: "text/javascript" }});
    const blobUrl = URL.createObjectURL(blob);
    import(blobUrl).then(async (mod) => {{
      const data = {json_str};
      const elements = data.elements || [];
      const appState = data.appState || {{}};
      const files = data.files || {{}};
      appState.viewBackgroundColor = appState.viewBackgroundColor || "{bg_color}";
      const svg = await mod.exportToSvg({{
        elements, appState: {{ ...appState, exportBackground: true }}, files
      }});
      svg.style.width = "100%";
      svg.style.height = "100%";
      document.getElementById("root").appendChild(svg);
    }});
  </script>"""
    else:
        script_block = f"""<script type="module">
    import {{ exportToSvg }} from "https://esm.sh/@excalidraw/excalidraw@{EXCALIDRAW_VERSION}?bundle";
    const data = {json_str};
    const elements = data.elements || [];
    const appState = data.appState || {{}};
    const files = data.files || {{}};
    appState.viewBackgroundColor = appState.viewBackgroundColor || "{bg_color}";
    const svg = await exportToSvg({{
      elements, appState: {{ ...appState, exportBackground: true }}, files
    }});
    svg.style.width = "100%";
    svg.style.height = "100%";
    document.getElementById("root").appendChild(svg);
  </script>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Excalidraw Diagram</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: {bg_color}; overflow: hidden; width: 100vw; height: 100vh; }}
    #root {{ width: 100%; height: 100%; }}
  </style>
</head>
<body>
  <div id="root"></div>
  {script_block}
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Watermark application (v2 2.1)
# ---------------------------------------------------------------------------
def _apply_watermark(png_path: Path) -> None:
    """Overlay a subtle attribution watermark on a rendered PNG (v2 2.1)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning(
            "Pillow not installed -- cannot add watermark. Run: uv pip install Pillow"
        )
        return
    try:
        img = Image.open(str(png_path)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text = "Created with excalidraw-diagram-skill"
        try:
            font = ImageFont.load_default()
        except OSError:
            font = None
        bbox = draw.textbbox((0, 0), text, font=font) if font else (0, 0, 220, 14)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        margin = 12
        pos = (img.width - tw - margin, img.height - th - margin)
        draw.rectangle(
            [pos[0] - 4, pos[1] - 2, pos[0] + tw + 4, pos[1] + th + 2],
            fill=(255, 255, 255, 160),
        )
        draw.text(pos, text, fill=(80, 80, 80, 200), font=font)
        combined = Image.alpha_composite(img, overlay).convert("RGB")
        combined.save(str(png_path))
    except Exception as e:
        logger.warning(f"Watermark application failed: {e}")


# ---------------------------------------------------------------------------
# JSON log formatter (v2 4.10)
# ---------------------------------------------------------------------------
class _JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        })


def _install_json_log_formatter() -> None:
    """Switch the module logger to emit JSON-line records on stderr (v2 4.10)."""
    for h in logger.handlers:
        h.setFormatter(_JsonLineFormatter())


# ---------------------------------------------------------------------------
# Help examples printer (v2 6.8)
# ---------------------------------------------------------------------------
_HELP_EXAMPLES = """\
# Render a diagram to PNG
uv run python render_excalidraw.py diagram.excalidraw

# Dark-mode render at 2x scale
uv run python render_excalidraw.py diagram.excalidraw --dark --scale 2

# Batch render every .excalidraw file in a directory
uv run python render_excalidraw.py --all ./examples

# Start a persistent server and POST a diagram via curl
uv run python render_excalidraw.py --server &
curl -X POST http://127.0.0.1:9120/render \\
  -H 'Content-Type: application/json' \\
  -d '{"data": {"type": "excalidraw", "elements": []}, "output": "out.png"}'

# Lint and auto-fix a diagram
uv run python lint_excalidraw.py diagram.excalidraw --fix

# Generate a shareable excalidraw.com URL
uv run python render_excalidraw.py diagram.excalidraw --url
"""


def _print_help_examples() -> None:
    print(_HELP_EXAMPLES)


# ---------------------------------------------------------------------------
# Self-test (v2 4.8)
# ---------------------------------------------------------------------------
_SELF_TEST_DIAGRAM = {
    "type": "excalidraw",
    "version": 2,
    "source": "self-test",
    "elements": [
        {
            "id": "r1", "type": "rectangle",
            "x": 100, "y": 100, "width": 120, "height": 60,
        }
    ],
    "appState": {"viewBackgroundColor": "#ffffff"},
    "files": {},
}


def _run_self_test() -> bool:
    """Render a canned 1-element diagram end-to-end. Returns True on success (v2 4.8)."""
    import tempfile
    ok = True
    try:
        tmp_in = tempfile.NamedTemporaryFile(suffix=".excalidraw", delete=False, mode="w")
        tmp_in.write(json.dumps(_SELF_TEST_DIAGRAM))
        tmp_in.close()
        tmp_out = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_out.close()
        try:
            render(
                Path(tmp_in.name), Path(tmp_out.name),
                scale=1, max_width=400,
            )
            # Validate the output via Pillow if available.
            try:
                from PIL import Image
                with Image.open(tmp_out.name) as im:
                    if im.size[0] < 20 or im.size[1] < 20:
                        logger.error("Self-test: output image too small")
                        ok = False
            except ImportError:
                pass
        finally:
            Path(tmp_in.name).unlink(missing_ok=True)
            Path(tmp_out.name).unlink(missing_ok=True)
        if ok:
            print("Self-test render: PASS")
        else:
            print("Self-test render: FAIL")
    except Exception as e:
        print(f"Self-test render: FAIL ({e})")
        ok = False
    return ok


# ---------------------------------------------------------------------------
# Batch render (v2 1.5, 2.4)
# ---------------------------------------------------------------------------
def _batch_render(
    inputs: list[Path],
    args,
    *,
    crop: tuple[int, int, int, int] | None,
) -> dict:
    """Render multiple .excalidraw files reusing a single Chromium browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenderError(
            "playwright not installed. Run: uv sync && uv run playwright install chromium"
        )

    template_html = _resolve_template_html()
    rendered: list[dict] = []
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"],
        )
        try:
            _ = browser.version
        except Exception:
            raise RenderError(
                "Chromium failed to start. Run `uv run playwright install chromium --with-deps`."
            )

        try:
            for inp in inputs:
                try:
                    raw = inp.read_text(encoding="utf-8-sig")
                    data = json.loads(raw)
                    errors = validate_excalidraw(data, max_elements=args.max_elements)
                    if errors:
                        raise RenderError("\n".join(errors))
                    # Apply theme.
                    if args.theme and args.theme != "default":
                        try:
                            from themes import apply_theme
                            apply_theme(data, args.theme)
                        except ImportError:
                            pass

                    out_path = inp.with_suffix(".png")
                    if args.svg:
                        out_path = inp.with_suffix(".svg")
                    elif args.pdf:
                        out_path = inp.with_suffix(".pdf")

                    active = [e for e in data.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")]
                    if active:
                        min_x, min_y, max_x, max_y = compute_bounding_box(active)
                        padding = 80
                        vp_w = min(int(max_x - min_x + padding * 2), args.width)
                        vp_h = min(max(int(max_y - min_y + padding * 2), 100), args.max_height)
                    else:
                        vp_w, vp_h = 800, 600

                    context = browser.new_context(
                        viewport={"width": vp_w, "height": vp_h},
                        device_scale_factor=args.scale,
                        permissions=[],
                    )
                    page = context.new_page()
                    try:
                        page.set_content(template_html)
                        page.wait_for_function("window.__moduleReady === true", timeout=30000)
                        page.evaluate("(data) => window.renderDiagram(data)", data)
                        page.wait_for_function(
                            "window.__renderComplete === true || window.__renderError !== null",
                            timeout=15000,
                        )
                        if args.svg:
                            svg_html = page.evaluate("""() => {
                                const svg = document.querySelector('#root svg');
                                return svg ? svg.outerHTML : null;
                            }""")
                            out_path.write_text(svg_html or "", encoding="utf-8")
                        elif args.pdf:
                            page.pdf(path=str(out_path), print_background=True)
                        else:
                            el = page.query_selector("#root svg")
                            if el is None:
                                raise RenderError("No SVG element found")
                            el.screenshot(path=str(out_path))
                            if args.watermark:
                                _apply_watermark(out_path)
                        rendered.append({"input": str(inp), "output": str(out_path), "success": True})
                    finally:
                        context.close()
                except Exception as e:
                    failed += 1
                    rendered.append({"input": str(inp), "success": False, "error": str(e)})
                    logger.error(f"{inp}: {e}")
        finally:
            browser.close()

    return {
        "rendered": sum(1 for r in rendered if r.get("success")),
        "failed": failed,
        "files": rendered,
    }


# ---------------------------------------------------------------------------
# Stats (v2 2.8)
# ---------------------------------------------------------------------------
def _print_stats(input_path: Path, *, json_output: bool = False) -> None:
    raw = input_path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    elements = [e for e in data.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")]
    type_counts: dict[str, int] = {}
    colors_fill: set[str] = set()
    colors_stroke: set[str] = set()
    sizes: list[float] = []
    text_in_container = 0
    text_free = 0
    arrows_bound = 0
    arrows_unbound = 0
    for el in elements:
        t = el.get("type", "?")
        type_counts[t] = type_counts.get(t, 0) + 1
        if "backgroundColor" in el and el["backgroundColor"] != "transparent":
            colors_fill.add(el["backgroundColor"])
        if "strokeColor" in el:
            colors_stroke.add(el["strokeColor"])
        try:
            w = abs(float(el.get("width", 0)))
            h = abs(float(el.get("height", 0)))
            if w and h:
                sizes.append(max(w, h))
        except (TypeError, ValueError):
            pass
        if t == "text":
            if el.get("containerId"):
                text_in_container += 1
            else:
                text_free += 1
        if t == "arrow":
            if el.get("startBinding") or el.get("endBinding"):
                arrows_bound += 1
            else:
                arrows_unbound += 1
    total_text = text_in_container + text_free
    pct_text_in_container = (text_in_container / total_text * 100) if total_text else 0.0
    median = 0.0
    if sizes:
        sizes_sorted = sorted(sizes)
        mid = len(sizes_sorted) // 2
        median = (
            sizes_sorted[mid] if len(sizes_sorted) % 2
            else (sizes_sorted[mid - 1] + sizes_sorted[mid]) / 2
        )
    stats = {
        "file": str(input_path),
        "elements_total": len(elements),
        "elements_by_type": type_counts,
        "distinct_fill_colors": len(colors_fill),
        "distinct_stroke_colors": len(colors_stroke),
        "distinct_shape_types": sum(1 for k in type_counts if k in ("rectangle", "ellipse", "diamond", "arrow", "line", "text", "frame", "image")),
        "text_in_container": text_in_container,
        "text_free": text_free,
        "text_in_container_pct": round(pct_text_in_container, 1),
        "arrows_bound": arrows_bound,
        "arrows_unbound": arrows_unbound,
        "avg_size_px": round(sum(sizes) / len(sizes), 1) if sizes else 0.0,
        "median_size_px": round(median, 1),
    }
    if json_output:
        print(json.dumps(stats, indent=2))
    else:
        print(f"Stats for {input_path.name}:")
        for k, v in stats.items():
            if k in ("file", "elements_by_type"):
                continue
            print(f"  {k}: {v}")
        print("  elements_by_type:")
        for t, n in sorted(type_counts.items()):
            print(f"    {t}: {n}")


# ---------------------------------------------------------------------------
# Open file (6.1)
# ---------------------------------------------------------------------------
def _open_file(path: Path) -> None:
    """Open a file with the system's default application."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(path)])
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            logger.warning(f"Cannot auto-open on {system}")
    except Exception as e:
        logger.warning(f"Failed to open {path}: {e}")


# ---------------------------------------------------------------------------
# Excalidraw URL generation (2.9)
# ---------------------------------------------------------------------------
def _generate_excalidraw_url(data: dict) -> str:
    """Generate a shareable excalidraw.com URL."""
    import base64
    import zlib

    json_bytes = json.dumps(data).encode("utf-8")
    compressed = zlib.compress(json_bytes)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
    return f"https://excalidraw.com/#json={encoded}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render Excalidraw JSON to PNG/SVG",
        epilog="""Examples:
  %(prog)s diagram.excalidraw
  %(prog)s diagram.excalidraw --scale 1 --width 1280
  %(prog)s diagram.excalidraw --svg
  %(prog)s diagram.excalidraw --dark
  %(prog)s diagram.excalidraw --dry-run --json
  %(prog)s diagram.excalidraw --format presentation
  %(prog)s - < diagram.excalidraw  (read from stdin)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input", type=str, nargs="*",
        help="Path to .excalidraw JSON file(s), or '-' to read from stdin. "
             "Multiple paths trigger batch mode that reuses Chromium (v2 1.5).",
    )
    parser.add_argument(
        "--all", dest="all_dir", type=Path, default=None,
        help="Batch-render every *.excalidraw file in the given directory, "
             "reusing a single Chromium instance (v2 2.4).",
    )
    parser.add_argument(
        "--help-examples", action="store_true",
        help="Print concrete copy-paste usage recipes and exit (v2 6.8).",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress INFO logging (only warnings/errors) (v2 6.10).",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Render a minimal canned diagram end-to-end to verify the pipeline (v2 4.8).",
    )
    parser.add_argument(
        "--theme", choices=["default", "warm", "cool", "high-contrast", "minimal"],
        default=None,
        help="Recolor elements using a preset palette from color-palette.md (v2 2.6).",
    )
    parser.add_argument(
        "--pdf", action="store_true",
        help="Render to PDF using Chromium's built-in PDF engine (v2 2.9).",
    )
    parser.add_argument(
        "--from-shortform", action="store_true",
        help="Treat input as shortform YAML-ish DSL; compile to Excalidraw JSON first (v2 2.10).",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print diagram metrics (element counts, color usage, etc.) (v2 2.8).",
    )
    parser.add_argument(
        "--html-inline", action="store_true",
        help="When exporting HTML, inline the vendor bundle for a self-contained file (v2 2.3).",
    )
    parser.add_argument(
        "--socket", type=str, default=None,
        help="UNIX domain socket path for --server mode (v2 5.3).",
    )
    parser.add_argument(
        "--output-root", type=Path, default=None,
        help="Restrict server mode writes to paths under this directory (v2 5.6).",
    )
    parser.add_argument(
        "--auth-token", action="store_true",
        help="Require Bearer token auth for server mode requests (v2 5.4).",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output file path (default: same name with .png/.svg suffix)",
    )
    parser.add_argument(
        "--scale", "-s", type=int, default=2,
        help="Device scale factor. scale=2 produces 2x resolution PNGs (default: 2). "
             "Use --scale 1 for faster draft renders (1.7)",
    )
    parser.add_argument(
        "--width", "-w", type=int, default=1920,
        help="Max viewport width in pixels (default: 1920). Diagrams wider than this are capped.",
    )
    parser.add_argument(
        "--max-height", type=int, default=MAX_HEIGHT_DEFAULT,
        help=f"Max viewport height in pixels (default: {MAX_HEIGHT_DEFAULT}). "
             "Prevents memory issues with very tall diagrams (3.4).",
    )
    parser.add_argument(
        "--timeout", "-t", type=int, default=30,
        help="Overall render timeout in seconds (default: 30). "
             "60%% for module loading, 40%% for render (3.8).",
    )
    parser.add_argument(
        "--svg", action="store_true",
        help="Output SVG instead of PNG. Faster, scalable (1.5).",
    )
    parser.add_argument(
        "--html", action="store_true",
        help="Output self-contained interactive HTML file (7.10).",
    )
    parser.add_argument(
        "--dark", action="store_true",
        help="Render in dark mode with dark background (2.3).",
    )
    parser.add_argument(
        "--crop", type=str, default=None,
        help="Crop region as x,y,width,height (e.g., --crop 500,0,700,800) (1.6).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-render even if cache is valid (4.6).",
    )
    parser.add_argument(
        "--max-elements", type=int, default=DEFAULT_MAX_ELEMENTS,
        help=f"Maximum element count (default: {DEFAULT_MAX_ELEMENTS}) (5.6).",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output structured JSON result instead of plain path (4.4).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate only, don't launch browser (4.9).",
    )
    parser.add_argument(
        "--open", action="store_true", dest="open_after",
        help="Open output file after rendering (6.1).",
    )
    parser.add_argument(
        "--url", action="store_true",
        help="Generate a shareable excalidraw.com URL (2.9).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging (4.3).",
    )
    parser.add_argument(
        "--format", choices=list(FORMAT_PRESETS.keys()), default=None,
        help="Output format preset: presentation (1920x1080), blog (800x600), "
             "thumbnail (400x300), social (1200x630) (6.9).",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Watch file for changes and re-render automatically (2.10).",
    )
    parser.add_argument(
        "--diff", type=Path, nargs="?", const=Path("__auto__"), default=None,
        help="Generate a diff against a prior PNG. If no path is provided, "
             "diffs against the auto-snapshot of the previous render (v2 2.2).",
    )
    parser.add_argument(
        "--watermark", action="store_true",
        help="Add subtle attribution watermark to output (7.8).",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verify installation: check Python, Playwright, Chromium, template (6.5).",
    )
    parser.add_argument(
        "--server", action="store_true",
        help="Start a persistent render server on localhost to avoid browser cold-start "
             "overhead. POST /render with JSON body to render (1.1).",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_SERVER_PORT,
        help=f"Port for --server mode (default: {DEFAULT_SERVER_PORT}) (1.1).",
    )
    args = parser.parse_args()

    # (v2 6.10) Quiet mode. Mutually exclusive with --verbose.
    if getattr(args, "quiet", False) and args.verbose:
        logger.error("--quiet and --verbose are mutually exclusive.")
        sys.exit(2)
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    elif getattr(args, "quiet", False):
        logger.setLevel(logging.WARNING)

    # (v2 4.10) JSON log formatter when --json is active so consumers get
    # machine-parseable stderr lines.
    if args.json_output:
        _install_json_log_formatter()

    # (v2 6.8) --help-examples prints copy-paste recipes.
    if args.help_examples:
        _print_help_examples()
        return

    # Installation check mode (6.5)
    if args.check:
        _verify_setup()
        return

    # (v2 4.8) Self-test renders a canned diagram end-to-end.
    if args.self_test:
        sys.exit(0 if _run_self_test() else 1)

    # Server mode (1.1)
    if args.server:
        try:
            start_server(
                port=args.port,
                output_root=args.output_root,
                socket_path=args.socket,
                require_auth=args.auth_token,
            )
        except RenderError as e:
            logger.error(str(e))
            sys.exit(1)
        return

    # Format preset override
    if args.format:
        preset = FORMAT_PRESETS[args.format]
        args.width = preset["width"]
        args.max_height = preset.get("height", MAX_HEIGHT_DEFAULT)
        args.scale = preset["scale"]
        # (v2 7.5) Print-quality preset: higher scale and vector-first output.
        if args.format == "print":
            args.scale = max(args.scale, 4)
    # (v2 7.5) Explicit "print" preset maps to high-DPI SVG output.
    if args.format == "print" and not args.svg and not args.pdf:
        args.svg = True

    # --all batch mode (v2 2.4). Collect inputs from directory.
    inputs: list[Path] = []
    if args.all_dir is not None:
        if not args.all_dir.is_dir():
            logger.error(f"--all requires a directory, got: {args.all_dir}")
            sys.exit(1)
        inputs.extend(sorted(args.all_dir.rglob("*.excalidraw")))
        if not inputs:
            logger.error(f"No .excalidraw files found under {args.all_dir}")
            sys.exit(1)

    stdin_tmp_path: Path | None = None
    if not inputs:
        if not args.input:
            logger.error("No input file(s) specified. Pass a path, use --all DIR, or '-' for stdin.")
            sys.exit(2)
        for raw_input in args.input:
            if raw_input == "-":
                import tempfile
                raw = sys.stdin.read()
                tmp = tempfile.NamedTemporaryFile(suffix=".excalidraw", delete=False, mode="w")
                tmp.write(raw)
                tmp.close()
                stdin_tmp_path = Path(tmp.name)
                inputs.append(stdin_tmp_path)
            else:
                inputs.append(Path(raw_input))

    for input_path in inputs:
        if not input_path.exists():
            logger.error(f"File not found: {input_path}")
            if stdin_tmp_path:
                stdin_tmp_path.unlink(missing_ok=True)
            sys.exit(1)

    # Path validation (5.3)
    if args.output and len(inputs) > 1:
        logger.error("--output cannot be combined with multiple inputs or --all.")
        sys.exit(2)
    if args.output:
        path_errors = validate_path(args.output, kind="output")
        if path_errors:
            for e in path_errors:
                logger.error(e)
            sys.exit(1)

    # Parse crop
    crop = None
    if args.crop:
        try:
            parts = [int(x.strip()) for x in args.crop.split(",")]
            if len(parts) != 4:
                raise ValueError("Need exactly 4 values")
            crop = (parts[0], parts[1], parts[2], parts[3])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid --crop format: {e}. Use: --crop x,y,width,height")
            sys.exit(1)

    # URL generation mode (2.9) -- single-input only.
    if args.url:
        if len(inputs) != 1:
            logger.error("--url only supports a single input file.")
            sys.exit(2)
        raw = inputs[0].read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        url = _generate_excalidraw_url(data)
        print(url)
        return

    # --stats mode (v2 2.8) -- single-input only.
    if args.stats:
        if len(inputs) != 1:
            logger.error("--stats only supports a single input file.")
            sys.exit(2)
        _print_stats(inputs[0], json_output=args.json_output)
        return

    # Watch mode (2.10) -- single-input only.
    if args.watch:
        if len(inputs) != 1:
            logger.error("--watch only supports a single input file.")
            sys.exit(2)
        _watch_and_render(inputs[0], args)
        return

    # (v2 2.10) Shortform DSL support.
    if args.from_shortform:
        from shortform import compile_shortform  # type: ignore
        new_inputs = []
        for p in inputs:
            raw = p.read_text(encoding="utf-8-sig")
            data = compile_shortform(raw)
            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                suffix=".excalidraw", delete=False, mode="w"
            )
            tmp.write(json.dumps(data))
            tmp.close()
            new_inputs.append(Path(tmp.name))
        inputs = new_inputs

    # Batch render (v2 1.5) when multiple inputs.
    try:
        if len(inputs) == 1:
            png_path = render(
                inputs[0],
                args.output,
                args.scale,
                args.width,
                max_height=args.max_height,
                timeout=args.timeout,
                svg_output=args.svg,
                html_output=args.html,
                dark_mode=args.dark,
                crop=crop,
                force=args.force,
                max_elements=args.max_elements,
                json_output=args.json_output,
                dry_run=args.dry_run,
                open_after=args.open_after,
                watermark=args.watermark,
                theme=args.theme,
                html_inline=args.html_inline,
                pdf_output=args.pdf,
            )
            # Diff mode (2.8, v2 2.2)
            if args.diff is not None and png_path.exists():
                # (v2 2.2) When --diff is used without a path, fall back to the
                # auto-saved snapshot captured before this render ran.
                diff_src = args.diff
                if str(args.diff) == str(Path("__auto__")):
                    diff_src = _LAST_PREV_SNAPSHOT.get(str(png_path))
                if diff_src:
                    _generate_diff(diff_src, png_path)
                else:
                    logger.warning(
                        "--diff requested but no prior render available to compare against."
                    )
        else:
            results = _batch_render(
                inputs, args, crop=crop,
            )
            if args.json_output:
                print(json.dumps(results, indent=2))
            else:
                for r in results["files"]:
                    print(r["output"] if r.get("success") else f"FAILED: {r.get('input')}")

    except RenderError as e:
        if args.json_output:
            print(json.dumps({"success": False, "errors": [str(e)]}, indent=2))
        else:
            logger.error(str(e))
        sys.exit(1)
    finally:
        # (v2 3.2) Clean up stdin temp file.
        if stdin_tmp_path is not None:
            try:
                stdin_tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Watch mode (2.10)
# ---------------------------------------------------------------------------
def _watch_and_render(input_path: Path, args) -> None:
    """Watch a file for changes and re-render."""
    logger.info(f"Watching {input_path} for changes (Ctrl+C to stop)...")
    last_mtime = 0.0
    try:
        while True:
            try:
                mtime = input_path.stat().st_mtime
            except OSError:
                time.sleep(1)
                continue
            if mtime > last_mtime:
                last_mtime = mtime
                logger.info("File changed, re-rendering...")
                try:
                    render(
                        input_path,
                        args.output,
                        args.scale,
                        args.width,
                        max_height=args.max_height,
                        timeout=args.timeout,
                        svg_output=args.svg,
                        html_output=args.html,
                        dark_mode=args.dark,
                        force=True,
                        max_elements=args.max_elements,
                        json_output=args.json_output,
                        open_after=args.open_after,
                    )
                except RenderError as e:
                    logger.error(str(e))
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Watch mode stopped.")


# ---------------------------------------------------------------------------
# Diff mode (2.8)
# ---------------------------------------------------------------------------
def _generate_diff(previous_png: Path, current_png: Path) -> None:
    """Generate a visual diff between two PNGs (basic pixel comparison)."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        logger.warning("Pillow not installed -- cannot generate diff. Run: pip install Pillow")
        return

    if not previous_png.exists():
        logger.warning(f"Previous PNG not found: {previous_png}")
        return

    try:
        img1 = Image.open(str(previous_png)).convert("RGB")
        img2 = Image.open(str(current_png)).convert("RGB")

        # Resize to match if different sizes
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        diff = ImageChops.difference(img1, img2)
        diff_path = current_png.with_stem(current_png.stem + "_diff")
        diff.save(str(diff_path))
        logger.info(f"Diff saved to {diff_path}")
    except Exception as e:
        logger.warning(f"Diff generation failed: {e}")


# ---------------------------------------------------------------------------
# Server mode (1.1) - Persistent browser for fast consecutive renders
# ---------------------------------------------------------------------------
DEFAULT_SERVER_PORT = 9120


class _RenderServer(http.server.BaseHTTPRequestHandler):
    """HTTP handler for render server mode. Holds a persistent browser context."""

    _playwright_ctx = None  # Set by start_server
    _page = None
    _template_html = None

    def log_message(self, format, *args):
        logger.debug(format % args)

    def do_POST(self):
        if self.path == "/render":
            self._handle_render()
        elif self.path == "/shutdown":
            self._handle_shutdown()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_error(404)

    def _send_json(self, status: int, payload: dict) -> None:
        """Send a JSON response with security headers (v2 5.2)."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _check_security(self) -> tuple[bool, str]:
        """Enforce Host header, auth token, and Origin policy (v2 5.2, 5.4)."""
        host = self.headers.get("Host", "")
        # Allow only 127.0.0.1[:port] or localhost
        host_lower = host.lower().split(":")[0]
        if host_lower not in ("127.0.0.1", "localhost", ""):
            return False, "Invalid Host header"
        origin = self.headers.get("Origin")
        if origin and origin != "null":
            # Only allow same-origin requests
            from urllib.parse import urlparse
            try:
                parsed = urlparse(origin)
                if parsed.hostname not in ("127.0.0.1", "localhost"):
                    return False, "Cross-origin requests rejected"
            except Exception:
                return False, "Malformed Origin header"
        required_token = getattr(_RenderServer, "_auth_token", None)
        if required_token:
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[len("Bearer "):] != required_token:
                return False, "Authentication required"
        return True, ""

    def _handle_render(self):
        ok, reason = self._check_security()
        if not ok:
            self._send_json(403, {"success": False, "error": reason})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return

        # (v2 5.5) Cap request body size.
        if length > MAX_FILE_SIZE_BYTES:
            self._send_json(413, {
                "success": False,
                "error": f"Payload too large (limit {MAX_FILE_SIZE_BYTES} bytes)",
            })
            return

        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as e:
            self._send_json(400, {"success": False, "error": str(e)})
            return

        excalidraw_data = body.get("data")
        output_path_str = body.get("output")
        svg_output = body.get("svg", False)
        scale = body.get("scale", 2)
        # (v2 3.4) Per-request timeout override, clamped to [1, 120].
        req_timeout = body.get("timeout", 15)
        try:
            req_timeout = max(1, min(120, int(req_timeout)))
        except (TypeError, ValueError):
            req_timeout = 15
        timeout_ms = req_timeout * 1000

        if not excalidraw_data or not output_path_str:
            self._send_json(400, {
                "success": False,
                "error": "Missing 'data' or 'output' in request body",
            })
            return

        output_path = Path(output_path_str)

        # (v2 5.6) Enforce output sandbox root when configured.
        output_root = getattr(_RenderServer, "_output_root", None)
        if output_root is not None:
            try:
                resolved = output_path.resolve()
                root_resolved = Path(output_root).resolve()
                if not str(resolved).startswith(str(root_resolved)):
                    self._send_json(403, {
                        "success": False,
                        "error": f"Output path outside sandbox ({root_resolved})",
                    })
                    return
            except OSError as e:
                self._send_json(400, {"success": False, "error": f"Bad output path: {e}"})
                return

        try:
            errors = validate_excalidraw(excalidraw_data)
            if errors:
                raise RenderError("Validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

            page = _RenderServer._page
            if page is None:
                raise RenderError("Server page not initialized")

            # (v2 1.1) Resize viewport per request from element bounding box.
            active = [e for e in excalidraw_data.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")]
            if active:
                min_x, min_y, max_x, max_y = compute_bounding_box(active)
                padding = 80
                vp_w = max(200, int(max_x - min_x + padding * 2))
                vp_h = max(200, int(max_y - min_y + padding * 2))
                # Cap width to something sane but allow tall diagrams
                vp_w = min(vp_w, 8000)
                vp_h = min(vp_h, MAX_HEIGHT_DEFAULT)
                try:
                    page.set_viewport_size({"width": vp_w, "height": vp_h})
                except Exception as e:
                    logger.debug(f"Viewport resize failed: {e}")

            # (v2 3.3) Reset render state AND previous SVG DOM between requests.
            page.evaluate(
                "() => { window.__renderComplete = false; "
                "window.__renderError = null; "
                "const r = document.getElementById('root'); if (r) r.innerHTML = ''; }"
            )

            result = page.evaluate("(data) => window.renderDiagram(data)", excalidraw_data)
            if not result or not result.get("success"):
                err_msg = result.get("error", "Unknown") if result else "null result"
                raise RenderError(f"Render failed: {err_msg}")

            # (v2 3.9) Wait for success OR error sentinel.
            page.wait_for_function(
                "window.__renderComplete === true || window.__renderError !== null",
                timeout=timeout_ms,
            )
            render_error = page.evaluate("() => window.__renderError")
            if render_error:
                raise RenderError(f"Render failed: {render_error}")

            if svg_output:
                svg_html = page.evaluate("""() => {
                    const svg = document.querySelector('#root svg');
                    return svg ? svg.outerHTML : null;
                }""")
                if not svg_html:
                    raise RenderError("No SVG element found")
                output_path.write_text(svg_html, encoding="utf-8")
            else:
                svg_el = page.query_selector("#root svg")
                if svg_el is None:
                    raise RenderError("No SVG element found")
                svg_el.screenshot(path=str(output_path))

            self._send_json(200, {"success": True, "output": str(output_path)})

        except (RenderError, Exception) as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def _handle_shutdown(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "shutting_down"}).encode())
        threading.Thread(target=self.server.shutdown).start()


def start_server(
    port: int = DEFAULT_SERVER_PORT,
    output_root: Path | None = None,
    socket_path: str | None = None,
    require_auth: bool = False,
) -> None:
    """Start a render server with a persistent Playwright browser (1.1).

    The server holds a single browser instance across all requests, eliminating
    the 1-3 second cold-start overhead per render. Send POST /render with JSON
    body {"data": <excalidraw_dict>, "output": "/path/to/output.png"}.

    POST /shutdown to stop the server.
    GET  /health for health check.

    (v2 1.1) Uses _resolve_template_html() so vendor bundle is honored.
    (v2 1.1) Resizes viewport per request based on diagram bounding box.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenderError(
            "playwright not installed. Run: cd references && uv sync && uv run playwright install chromium"
        )

    # (v2 1.1) Use the shared resolver so vendor bundle is used when available.
    template_html = _resolve_template_html()

    logger.info("Starting persistent browser...")
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--disable-gpu", "--disable-dev-shm-usage"],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=2,
        permissions=[],
    )
    page = context.new_page()
    page.set_content(template_html)

    try:
        page.wait_for_function("window.__moduleReady === true", timeout=30000)
    except Exception:
        browser.close()
        pw.stop()
        raise RenderError("Failed to load Excalidraw library in server mode")

    _RenderServer._page = page
    _RenderServer._template_html = template_html
    _RenderServer._output_root = output_root  # (v2 5.6)
    _RenderServer._server_ref = None  # set below

    # (v2 5.4) Generate auth token if requested, write to cache dir with 0o600.
    if require_auth:
        import secrets
        token = secrets.token_hex(32)
        _RenderServer._auth_token = token
        cache_dir = Path.home() / ".cache" / "excalidraw-diagram-skill"
        cache_dir.mkdir(parents=True, exist_ok=True)
        token_path = cache_dir / "token"
        token_path.write_text(token, encoding="utf-8")
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
        logger.info(f"Auth token stored at {token_path}")
    else:
        _RenderServer._auth_token = None

    # (v2 5.3) Optional UNIX domain socket binding instead of TCP.
    if socket_path:
        if platform.system() == "Windows":
            logger.warning("UNIX sockets unsupported on Windows -- falling back to TCP")
            server = http.server.HTTPServer(("127.0.0.1", port), _RenderServer)
        else:
            import socket as _socket
            if Path(socket_path).exists():
                Path(socket_path).unlink()

            class _UDSServer(http.server.HTTPServer):
                address_family = _socket.AF_UNIX

            server = _UDSServer(socket_path, _RenderServer)
            try:
                os.chmod(socket_path, 0o600)
            except OSError:
                pass
            logger.info(f"Render server listening on unix:{socket_path}")
    else:
        server = http.server.HTTPServer(("127.0.0.1", port), _RenderServer)
        logger.info(f"Render server listening on http://127.0.0.1:{port}")
    _RenderServer._server_ref = server
    logger.info("POST /render  - render a diagram")
    logger.info("POST /shutdown - stop the server")
    logger.info("GET  /health  - health check")

    # (v2 3.6) Handle SIGTERM gracefully -- don't leak the browser.
    import signal as _signal

    def _shutdown_handler(_signum, _frame):  # pragma: no cover (signal path)
        threading.Thread(target=server.shutdown).start()
    try:
        _signal.signal(_signal.SIGTERM, _shutdown_handler)
    except (AttributeError, ValueError):
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down server...")
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass
        logger.info("Server stopped.")


# ---------------------------------------------------------------------------
# Setup verification (6.5)
# ---------------------------------------------------------------------------
def _verify_setup() -> None:
    """Verify that all dependencies are installed and working (v2 4.8, 6.6)."""
    checks = []

    # Check Python version
    py_version = sys.version_info
    ok = py_version >= (3, 11)
    checks.append(("Python >= 3.11", ok, f"{py_version.major}.{py_version.minor}.{py_version.micro}"))

    # Check Playwright import
    try:
        import playwright  # noqa: F401
        checks.append(("Playwright installed", True, "OK"))
    except ImportError:
        checks.append(("Playwright installed", False, "Run: uv sync"))

    # Check template file
    template_path = Path(__file__).parent / "render_template.html"
    checks.append(("Template file exists", template_path.exists(), str(template_path)))

    # Check Chromium
    system = platform.system()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        checks.append(("Chromium installed", True, "OK"))
    except Exception as e:
        # (v2 6.6) OS-specific guidance.
        if system == "Linux":
            hint = "Run: uv run playwright install chromium --with-deps"
        elif system == "Darwin":
            hint = (
                "Run: uv run playwright install chromium  "
                "(on Apple Silicon, if it fails with NSInternalInconsistencyException, "
                "try `uv run playwright install --force chromium`)"
            )
        elif system == "Windows":
            hint = "Run: uv run playwright install chromium"
        else:
            hint = "Run: uv run playwright install chromium"
        checks.append(("Chromium installed", False, f"{hint} ({e})"))

    # (v2 4.7) Vendor bundle version drift check.
    if (VENDOR_DIR / "integrity.json").exists():
        try:
            integrity = json.loads((VENDOR_DIR / "integrity.json").read_text(encoding="utf-8"))
            if integrity.get("version") != EXCALIDRAW_VERSION:
                checks.append((
                    "Vendor bundle version", False,
                    f"bundle={integrity.get('version')} code={EXCALIDRAW_VERSION} -- rerun vendor_excalidraw.py",
                ))
            else:
                checks.append(("Vendor bundle version", True, integrity.get("version")))
        except (OSError, json.JSONDecodeError):
            pass

    # Print results
    all_ok = True
    for name, ok_, detail in checks:
        status = "PASS" if ok_ else "FAIL"
        if not ok_:
            all_ok = False
        print(f"  [{status}] {name}: {detail}")

    # (v2 4.8) Run a real end-to-end render as the final check.
    if all_ok:
        print("\nRunning self-test render...")
        if _run_self_test():
            print("All checks passed. Setup is complete.")
        else:
            print("\nSelf-test render FAILED.")
            sys.exit(1)
    else:
        print("\nSome checks failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
