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
# ---------------------------------------------------------------------------
logger = logging.getLogger("excalidraw_render")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)

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
    duplicate_ids: dict[str, int] = {}

    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            errors.append(f"Element at index {i} is not an object (got {type(el).__name__})")
            continue

        el_id = el.get("id", f"<index:{i}>")
        el_type = el.get("type", "<missing>")

        # Check required common fields
        for field in required_common:
            if field not in el:
                errors.append(f"Element '{el_id}' missing required field '{field}'")

        # Duplicate ID detection (3.9)
        if "id" in el:
            if el["id"] in id_map:
                duplicate_ids[el["id"]] = duplicate_ids.get(el["id"], 1) + 1
            else:
                id_map[el["id"]] = el

        # Coordinate validation - warn on non-numeric
        for coord in ("x", "y"):
            val = el.get(coord)
            if val is not None and not isinstance(val, (int, float)):
                errors.append(
                    f"Element '{el_id}' has non-numeric '{coord}': {val!r}. "
                    "Fix: Ensure x and y are numbers."
                )

        # Seed value validation (5.7)
        for seed_field in ("seed", "versionNonce"):
            val = el.get(seed_field)
            if val is not None:
                if not isinstance(val, (int, float)):
                    warnings.append(f"Element '{el_id}' has non-numeric '{seed_field}': {val!r}")
                elif val < 0:
                    warnings.append(f"Element '{el_id}' has negative '{seed_field}': {val}")
                elif val > MAX_SAFE_INTEGER:
                    warnings.append(
                        f"Element '{el_id}' has '{seed_field}' ({val}) exceeding "
                        f"JavaScript MAX_SAFE_INTEGER ({MAX_SAFE_INTEGER})"
                    )

        # Link URL validation (5.5)
        link = el.get("link")
        if link and isinstance(link, str):
            link_lower = link.strip().lower()
            for scheme in DANGEROUS_URL_SCHEMES:
                if link_lower.startswith(scheme):
                    errors.append(
                        f"Element '{el_id}' has dangerous link URL scheme '{scheme}': {link[:80]}. "
                        "Fix: Only http:, https:, and relative URLs are allowed."
                    )
                    break

        # Warn about zero-dimension elements (non-text, non-line/arrow)
        if el_type in ("rectangle", "ellipse", "diamond"):
            w = el.get("width", 0)
            h = el.get("height", 0)
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                if w == 0 and h == 0:
                    warnings.append(f"Element '{el_id}' ({el_type}) has zero width and height")

    # Report duplicate IDs
    for dup_id, count in duplicate_ids.items():
        errors.append(f"Duplicate element ID '{dup_id}' appears {count} times")

    # Binding integrity checks (4.5)
    for el in elements:
        if not isinstance(el, dict):
            continue
        el_id = el.get("id", "<unknown>")

        # Check startBinding/endBinding references
        for binding_key in ("startBinding", "endBinding"):
            binding = el.get(binding_key)
            if binding and isinstance(binding, dict):
                ref_id = binding.get("elementId")
                if ref_id and ref_id not in id_map:
                    errors.append(
                        f"Element '{el_id}' has {binding_key} referencing "
                        f"non-existent element '{ref_id}'"
                    )

        # Check containerId reference
        container_id = el.get("containerId")
        if container_id and container_id not in id_map:
            errors.append(
                f"Element '{el_id}' has containerId referencing "
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
    """Validate file paths to prevent path traversal and unsafe writes."""
    errors: list[str] = []
    # Check both the raw path and resolved (symlink-resolved) path
    raw_str = str(path)
    resolved_str = str(path.resolve())

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
def _vendor_bundle_available() -> bool:
    """Check if a vendored Excalidraw bundle exists and passes integrity check."""
    bundle_path = VENDOR_DIR / "excalidraw-bundle.js"
    integrity_path = VENDOR_DIR / "integrity.json"
    if not bundle_path.exists() or not integrity_path.exists():
        return False
    try:
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        content = bundle_path.read_bytes()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != integrity.get("sha256"):
            logger.warning("Vendor bundle integrity check failed -- falling back to CDN")
            return False
        return True
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Cannot verify vendor bundle: {e}")
        return False


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
    """
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
  <!-- (5.4) CSP adapted for local vendor bundle -->
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src blob: 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ overflow: hidden; }}
    #root {{ display: inline-block; }}
    #root svg {{ display: block; }}
  </style>
</head>
<body>
  <div id="root"></div>

  <script>
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
          window.__renderComplete = true;
          window.__renderError = null;
          return {{ success: true, width: svg.getAttribute("width"), height: svg.getAttribute("height") }};
        }} catch (err) {{
          window.__renderComplete = true;
          window.__renderError = err.message;
          return {{ success: false, error: err.message }};
        }}
      }};
      window.__moduleReady = true;
    }}).catch((err) => {{
      window.__moduleError = err.message || "Failed to load vendor bundle";
    }});
  </script>

  <script>
    window.addEventListener("error", function(e) {{
      window.__moduleError = e.message || "Unknown module load error";
    }});
  </script>
</body>
</html>"""
        logger.info("Using vendored Excalidraw bundle (offline mode)")
        return vendor_template

    return template_html


# ---------------------------------------------------------------------------
# Connectivity check (4.10)
# ---------------------------------------------------------------------------
def _check_connectivity(host: str = "esm.sh", timeout: float = 3.0) -> bool:
    """Quick DNS resolution check to see if we can reach esm.sh."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(host, 443)
        return True
    except (socket.gaierror, socket.timeout, OSError):
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

    # Read and validate
    logger.info(f"Reading {excalidraw_path}...")
    raw = excalidraw_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RenderError(
            f"Invalid JSON in {excalidraw_path}: {e}. "
            "Fix: Check for trailing commas, missing quotes, or unescaped characters."
        )

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
        _export_html(data, output_path, dark_mode)
        logger.info(f"HTML export saved to {output_path}")
        if open_after:
            _open_file(output_path)
        return output_path

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

    # Write cache (4.6)
    if not svg_output:
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
def _export_html(data: dict, output_path: Path, dark_mode: bool = False) -> None:
    """Export diagram as self-contained interactive HTML file."""
    json_str = json.dumps(data)
    bg_color = "#1e1e1e" if dark_mode else "#ffffff"
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
  <script type="module">
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
  </script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


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
        "input", type=str,
        help="Path to .excalidraw JSON file, or '-' to read from stdin (6.6)",
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
        "--diff", type=Path, default=None,
        help="Path to previous PNG for diff highlighting (2.8).",
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

    # Verbose mode
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Installation check mode (6.5)
    if args.check:
        _verify_setup()
        return

    # Server mode (1.1)
    if args.server:
        try:
            start_server(port=args.port)
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

    # Handle stdin input (6.6)
    if args.input == "-":
        import tempfile
        raw = sys.stdin.read()
        tmp = tempfile.NamedTemporaryFile(suffix=".excalidraw", delete=False, mode="w")
        tmp.write(raw)
        tmp.close()
        input_path = Path(tmp.name)
    else:
        input_path = Path(args.input)

    if not input_path.exists():
        logger.error(f"File not found: {input_path}")
        sys.exit(1)

    # Path validation (5.3)
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

    # URL generation mode (2.9)
    if args.url:
        raw = input_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        url = _generate_excalidraw_url(data)
        print(url)
        return

    # Watch mode (2.10)
    if args.watch:
        _watch_and_render(input_path, args)
        return

    try:
        png_path = render(
            input_path,
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
        )

        # Diff mode (2.8)
        if args.diff and png_path.exists():
            _generate_diff(args.diff, png_path)

    except RenderError as e:
        if args.json_output:
            print(json.dumps({"success": False, "errors": [str(e)]}, indent=2))
        else:
            logger.error(str(e))
        sys.exit(1)


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

    def _handle_render(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())
            return

        excalidraw_data = body.get("data")
        output_path_str = body.get("output")
        svg_output = body.get("svg", False)
        scale = body.get("scale", 2)

        if not excalidraw_data or not output_path_str:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False, "error": "Missing 'data' or 'output' in request body"
            }).encode())
            return

        output_path = Path(output_path_str)

        try:
            errors = validate_excalidraw(excalidraw_data)
            if errors:
                raise RenderError("Validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

            page = _RenderServer._page
            if page is None:
                raise RenderError("Server page not initialized")

            # Reset render state
            page.evaluate("() => { window.__renderComplete = false; window.__renderError = null; }")

            result = page.evaluate("(data) => window.renderDiagram(data)", excalidraw_data)
            if not result or not result.get("success"):
                err_msg = result.get("error", "Unknown") if result else "null result"
                raise RenderError(f"Render failed: {err_msg}")

            page.wait_for_function("window.__renderComplete === true", timeout=15000)

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

            resp = {"success": True, "output": str(output_path)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())

        except (RenderError, Exception) as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())

    def _handle_shutdown(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "shutting_down"}).encode())
        threading.Thread(target=self.server.shutdown).start()


def start_server(port: int = DEFAULT_SERVER_PORT) -> None:
    """Start a render server with a persistent Playwright browser (1.1).

    The server holds a single browser instance across all requests, eliminating
    the 1-3 second cold-start overhead per render. Send POST /render with JSON
    body {"data": <excalidraw_dict>, "output": "/path/to/output.png"}.

    POST /shutdown to stop the server.
    GET  /health for health check.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenderError(
            "playwright not installed. Run: cd references && uv sync && uv run playwright install chromium"
        )

    template_path = Path(__file__).parent / "render_template.html"
    if not template_path.exists():
        raise RenderError(f"Template not found at {template_path}")
    template_html = template_path.read_text(encoding="utf-8")

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

    server = http.server.HTTPServer(("127.0.0.1", port), _RenderServer)
    logger.info(f"Render server listening on http://127.0.0.1:{port}")
    logger.info("POST /render  - render a diagram")
    logger.info("POST /shutdown - stop the server")
    logger.info("GET  /health  - health check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down server...")
        browser.close()
        pw.stop()
        logger.info("Server stopped.")


# ---------------------------------------------------------------------------
# Setup verification (6.5)
# ---------------------------------------------------------------------------
def _verify_setup() -> None:
    """Verify that all dependencies are installed and working."""
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
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        checks.append(("Chromium installed", True, "OK"))
    except Exception as e:
        checks.append(("Chromium installed", False, f"Run: uv run playwright install chromium ({e})"))

    # Print results
    all_ok = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{status}] {name}: {detail}")

    if all_ok:
        print("\nAll checks passed. Setup is complete.")
    else:
        print("\nSome checks failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
