"""Generate an animated GIF demonstrating the render-fix loop (7.2).

This script programmatically creates a series of diagram states (frames)
showing the iterative improvement process, then assembles them into an
animated GIF. No terminal recording tool (asciinema) is needed.

Usage:
    cd references
    uv run python generate_demo_gif.py [--output ../examples/render-fix-loop.gif]

Requires: Pillow (pip install Pillow)

The GIF shows 5 frames:
  Frame 1: Initial draft with overlapping elements (bad)
  Frame 2: Validation warning overlay
  Frame 3: Elements repositioned (fix spacing)
  Frame 4: Colors applied (semantic coloring)
  Frame 5: Final polished diagram (done)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow is required. Install it with: pip install Pillow")
    sys.exit(1)


# Frame dimensions
WIDTH = 800
HEIGHT = 500
BG_COLOR = "#ffffff"
# (v2 7.6) Per-frame duration halved; combined with intermediate tween frames
# we get smoother motion without dragging total length.
FRAME_DURATION_MS = 900
BRAND_URL = "github.com/welshofer/excalidraw-diagram-skill"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _draw_rounded_rect(draw, xy, fill, outline, radius=8, width=2):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _draw_box(draw, x, y, w, h, fill, stroke, text, text_color="#000000", font=None):
    _draw_rounded_rect(draw, (x, y, x + w, y + h), fill=fill, outline=stroke)
    if font:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x + w / 2 - tw / 2, y + h / 2 - th / 2), text, fill=text_color, font=font)
    else:
        draw.text((x + 10, y + 10), text, fill=text_color)


def _draw_arrow(draw, x1, y1, x2, y2, color, width=2):
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    # Arrowhead
    import math

    angle = math.atan2(y2 - y1, x2 - x1)
    arrow_len = 10
    ax1 = x2 - arrow_len * math.cos(angle - 0.4)
    ay1 = y2 - arrow_len * math.sin(angle - 0.4)
    ax2 = x2 - arrow_len * math.cos(angle + 0.4)
    ay2 = y2 - arrow_len * math.sin(angle + 0.4)
    draw.polygon([(x2, y2), (int(ax1), int(ay1)), (int(ax2), int(ay2))], fill=color)


def _get_font(size=16):
    """Try to load a good font, fall back to default."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_title_bar(draw, text, step_num, total_steps, font_title, font_small):
    # Background bar
    draw.rectangle([(0, 0), (WIDTH, 50)], fill="#1e293b")
    draw.text((20, 12), f"Step {step_num}/{total_steps}: {text}", fill="#f8fafc", font=font_title)
    # Progress dots
    for i in range(total_steps):
        cx = WIDTH - 30 - (total_steps - 1 - i) * 20
        color = "#3b82f6" if i < step_num else "#475569"
        draw.ellipse([(cx - 5, 20), (cx + 5, 30)], fill=color)


def frame_1_initial_draft(font, font_small, font_title) -> Image.Image:
    """Frame 1: Initial draft with poor layout."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    _draw_title_bar(draw, "Generate initial JSON", 1, 5, font_title, font_small)

    # All boxes same gray, stacked vertically, overlapping
    gray = "#e5e7eb"
    stroke = "#6b7280"

    _draw_box(draw, 100, 80, 120, 55, gray, stroke, "User", font=font)
    _draw_box(draw, 100, 160, 120, 55, gray, stroke, "API", font=font)
    _draw_box(draw, 100, 240, 120, 55, gray, stroke, "Auth", font=font)
    _draw_box(draw, 100, 320, 120, 55, gray, stroke, "Database", font=font)

    _draw_arrow(draw, 160, 135, 160, 160, stroke)
    _draw_arrow(draw, 160, 215, 160, 240, stroke)
    _draw_arrow(draw, 160, 295, 160, 320, stroke)

    # Problem indicators
    draw.text((300, 120), "All same color", fill="#dc2626", font=font_small)
    draw.text((300, 150), "All same size", fill="#dc2626", font=font_small)
    draw.text((300, 180), "No visual hierarchy", fill="#dc2626", font=font_small)
    draw.text((300, 210), "Single column stack", fill="#dc2626", font=font_small)

    return img


def frame_2_validation(font, font_small, font_title) -> Image.Image:
    """Frame 2: Validation overlay showing issues."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    _draw_title_bar(draw, "Render & validate", 2, 5, font_title, font_small)

    # Same layout as frame 1 but with warning overlays
    gray = "#e5e7eb"
    stroke = "#6b7280"

    _draw_box(draw, 100, 80, 120, 55, gray, stroke, "User", font=font)
    _draw_box(draw, 100, 160, 120, 55, gray, stroke, "API", font=font)
    _draw_box(draw, 100, 240, 120, 55, gray, stroke, "Auth", font=font)
    _draw_box(draw, 100, 320, 120, 55, gray, stroke, "Database", font=font)

    _draw_arrow(draw, 160, 135, 160, 160, stroke)
    _draw_arrow(draw, 160, 215, 160, 240, stroke)
    _draw_arrow(draw, 160, 295, 160, 320, stroke)

    # Warning panel
    draw.rectangle([(320, 80), (750, 400)], fill="#fef2f2", outline="#dc2626", width=2)
    draw.text((340, 95), "Lint Results:", fill="#dc2626", font=font)
    warnings = [
        "[WARN] spacing-inconsistent: tight vertical",
        "[WARN] No shape differentiation (all rects)",
        "[INFO] No semantic color coding",
        "[INFO] API is central but not visually dominant",
        "[WARN] Auth is dependency, not in fan-out",
        "",
        "Suggested fixes:",
        "  - Use fan-out from API to Auth + DB",
        "  - Vary shape types for different roles",
        "  - Apply semantic colors from palette",
        "  - Make API box larger (it's the hub)",
    ]
    y_off = 125
    for line in warnings:
        color = "#dc2626" if "[WARN]" in line else "#1e3a5f"
        draw.text((340, y_off), line, fill=color, font=font_small)
        y_off += 22

    return img


def frame_3_fix_layout(font, font_small, font_title) -> Image.Image:
    """Frame 3: Repositioned with fan-out pattern."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    _draw_title_bar(draw, "Fix layout (fan-out pattern)", 3, 5, font_title, font_small)

    gray = "#e5e7eb"
    stroke = "#6b7280"

    # Ellipse for user (different shape)
    draw.ellipse([(60, 160), (180, 230)], fill=gray, outline=stroke, width=2)
    bbox = font.getbbox("User")
    draw.text((120 - (bbox[2] - bbox[0]) // 2, 185), "User", fill="#374151", font=font)

    # Larger central API box
    _draw_box(draw, 260, 150, 180, 80, gray, stroke, "API Gateway", font=font)

    # Fan-out to Auth and DB
    _draw_box(draw, 530, 100, 140, 55, gray, stroke, "Auth", font=font)
    draw.ellipse([(550, 270), (670, 340)], fill=gray, outline=stroke, width=2)
    bbox = font.getbbox("Database")
    draw.text((610 - (bbox[2] - bbox[0]) // 2, 295), "Database", fill="#374151", font=font)

    _draw_arrow(draw, 180, 195, 260, 190, stroke, width=2)
    _draw_arrow(draw, 440, 170, 530, 127, stroke, width=2)
    _draw_arrow(draw, 440, 210, 550, 290, stroke, width=2)

    # Improvement notes
    draw.text(
        (300, 400), "Fan-out pattern applied. Shape variety added.", fill="#059669", font=font_small
    )

    return img


def frame_4_apply_colors(font, font_small, font_title) -> Image.Image:
    """Frame 4: Colors applied from semantic palette."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    _draw_title_bar(draw, "Apply semantic colors", 4, 5, font_title, font_small)

    # User (orange/external)
    draw.ellipse([(60, 160), (180, 230)], fill="#fed7aa", outline="#c2410c", width=2)
    bbox = font.getbbox("User")
    draw.text((120 - (bbox[2] - bbox[0]) // 2, 185), "User", fill="#c2410c", font=font)

    # API (blue/primary)
    _draw_box(
        draw,
        260,
        150,
        180,
        80,
        "#3b82f6",
        "#1e3a5f",
        "API Gateway",
        text_color="#ffffff",
        font=font,
    )

    # Auth (amber/warning)
    _draw_box(
        draw, 530, 100, 140, 55, "#fef3c7", "#b45309", "Auth", text_color="#b45309", font=font
    )

    # Database (green/data)
    draw.ellipse([(550, 270), (670, 340)], fill="#a7f3d0", outline="#047857", width=2)
    bbox = font.getbbox("Database")
    draw.text((610 - (bbox[2] - bbox[0]) // 2, 295), "Database", fill="#047857", font=font)

    _draw_arrow(draw, 180, 195, 260, 190, "#c2410c", width=2)
    _draw_arrow(draw, 440, 170, 530, 127, "#b45309", width=2)
    _draw_arrow(draw, 440, 210, 550, 290, "#1e3a5f", width=2)

    # Labels
    draw.text((470, 150), "verify", fill="#b45309", font=font_small)
    draw.text((470, 240), "query", fill="#1e3a5f", font=font_small)
    draw.text((190, 170), "HTTPS", fill="#c2410c", font=font_small)

    draw.text(
        (250, 400),
        "Semantic colors applied: each role has its own color.",
        fill="#059669",
        font=font_small,
    )

    return img


def frame_5_final(font, font_small, font_title) -> Image.Image:
    """Frame 5: Final polished result."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    _draw_title_bar(draw, "Final result", 5, 5, font_title, font_small)

    # Title
    title_font = _get_font(20)
    draw.text((250, 70), "System Architecture", fill="#1e40af", font=title_font)

    # User (orange/external)
    draw.ellipse([(60, 140), (180, 210)], fill="#fed7aa", outline="#c2410c", width=2)
    bbox = font.getbbox("User")
    draw.text((120 - (bbox[2] - bbox[0]) // 2, 165), "User", fill="#c2410c", font=font)

    # API (blue/primary) - dominant
    _draw_box(
        draw,
        260,
        120,
        180,
        80,
        "#3b82f6",
        "#1e3a5f",
        "API Gateway",
        text_color="#ffffff",
        font=font,
    )

    # Auth (amber)
    _draw_box(
        draw, 530, 100, 140, 55, "#fef3c7", "#b45309", "Auth", text_color="#b45309", font=font
    )
    draw.text((555, 160), "JWT + OAuth 2.0", fill="#92400e", font=font_small)

    # Database (green)
    draw.ellipse([(550, 240), (680, 310)], fill="#a7f3d0", outline="#047857", width=2)
    bbox = font.getbbox("PostgreSQL")
    draw.text((615 - (bbox[2] - bbox[0]) // 2, 265), "PostgreSQL", fill="#047857", font=font)
    draw.text((560, 315), "Primary + Replica", fill="#065f46", font=font_small)

    _draw_arrow(draw, 180, 175, 260, 165, "#c2410c", width=2)
    _draw_arrow(draw, 440, 145, 530, 127, "#b45309", width=2)
    _draw_arrow(draw, 440, 185, 560, 265, "#1e3a5f", width=2)

    draw.text((190, 148), "HTTPS", fill="#c2410c", font=font_small)
    draw.text((475, 120), "verify", fill="#b45309", font=font_small)
    draw.text((470, 215), "query", fill="#1e3a5f", font=font_small)

    # Success banner
    draw.rectangle([(150, 380), (650, 430)], fill="#ecfdf5", outline="#059669", width=2)
    draw.text((200, 392), "Diagram argues visually. Ready to ship.", fill="#047857", font=font)

    return img


def generate_gif(output_path: Path) -> None:
    """Generate the animated GIF showing the render-fix loop."""
    font = _get_font(16)
    font_small = _get_font(12)
    font_title = _get_font(16)

    frames = [
        frame_1_initial_draft(font, font_small, font_title),
        frame_2_validation(font, font_small, font_title),
        frame_3_fix_layout(font, font_small, font_title),
        frame_4_apply_colors(font, font_small, font_title),
        frame_5_final(font, font_small, font_title),
    ]

    # Save as animated GIF
    frames[0].save(
        str(output_path),
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,  # infinite loop
    )
    print(f"Generated animated GIF: {output_path} ({output_path.stat().st_size:,} bytes)")
    print(f"  Frames: {len(frames)}")
    print(f"  Duration per frame: {FRAME_DURATION_MS}ms")
    print(f"  Total duration: {FRAME_DURATION_MS * len(frames) / 1000:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate render-fix loop animated GIF (7.2)")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(__file__).parent.parent / "examples" / "render-fix-loop.gif",
        help="Output GIF path",
    )
    args = parser.parse_args()
    generate_gif(args.output)


if __name__ == "__main__":
    main()
