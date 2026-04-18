"""Tests for animated GIF generation (7.2)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from PIL import Image

    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

from generate_demo_gif import (
    _hex_to_rgb,
    _get_font,
    frame_1_initial_draft,
    frame_2_validation,
    frame_3_fix_layout,
    frame_4_apply_colors,
    frame_5_final,
    generate_gif,
    WIDTH,
    HEIGHT,
)


@pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
class TestGifFrameGeneration:
    """Test individual frame generation."""

    @pytest.fixture
    def fonts(self):
        font = _get_font(16)
        font_small = _get_font(12)
        font_title = _get_font(16)
        return font, font_small, font_title

    def test_frame_1_creates_image(self, fonts):
        img = frame_1_initial_draft(*fonts)
        assert img.size == (WIDTH, HEIGHT)
        assert img.mode == "RGB"

    def test_frame_2_creates_image(self, fonts):
        img = frame_2_validation(*fonts)
        assert img.size == (WIDTH, HEIGHT)

    def test_frame_3_creates_image(self, fonts):
        img = frame_3_fix_layout(*fonts)
        assert img.size == (WIDTH, HEIGHT)

    def test_frame_4_creates_image(self, fonts):
        img = frame_4_apply_colors(*fonts)
        assert img.size == (WIDTH, HEIGHT)

    def test_frame_5_creates_image(self, fonts):
        img = frame_5_final(*fonts)
        assert img.size == (WIDTH, HEIGHT)


@pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
class TestGifGeneration:
    """Test full GIF generation."""

    def test_generates_gif_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.gif"
            generate_gif(output)
            assert output.exists()
            assert output.stat().st_size > 0

    def test_gif_is_valid_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.gif"
            generate_gif(output)
            img = Image.open(str(output))
            assert img.format == "GIF"
            assert img.is_animated
            assert img.n_frames == 5

    def test_gif_dimensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.gif"
            generate_gif(output)
            img = Image.open(str(output))
            assert img.size == (WIDTH, HEIGHT)


class TestHelperFunctions:
    """Test helper utilities."""

    def test_hex_to_rgb(self):
        assert _hex_to_rgb("#ff0000") == (255, 0, 0)
        assert _hex_to_rgb("#00ff00") == (0, 255, 0)
        assert _hex_to_rgb("#0000ff") == (0, 0, 255)
        assert _hex_to_rgb("#ffffff") == (255, 255, 255)

    def test_hex_to_rgb_without_hash(self):
        assert _hex_to_rgb("ff0000") == (255, 0, 0)

    @pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
    def test_get_font_returns_something(self):
        font = _get_font(16)
        assert font is not None
