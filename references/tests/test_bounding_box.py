"""Tests for compute_bounding_box() function."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from render_excalidraw import compute_bounding_box


def _el(id="el1", type="rectangle", x=0, y=0, w=100, h=50, **kwargs):
    """Helper to create a minimal element."""
    el = {"id": id, "type": type, "x": x, "y": y, "width": w, "height": h}
    el.update(kwargs)
    return el


class TestBasicBoundingBox:
    """Test basic bounding box computation."""

    def test_single_rectangle(self):
        elements = [_el(x=100, y=200, w=300, h=150)]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 100
        assert min_y == 200
        assert max_x == 400
        assert max_y == 350

    def test_two_rectangles(self):
        elements = [
            _el(id="r1", x=0, y=0, w=100, h=50),
            _el(id="r2", x=200, y=300, w=100, h=50),
        ]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 0
        assert min_y == 0
        assert max_x == 300
        assert max_y == 350

    def test_empty_elements(self):
        """Empty list returns default bounding box."""
        result = compute_bounding_box([])
        assert result == (0, 0, 800, 600)

    def test_deleted_elements_ignored(self):
        elements = [
            _el(id="visible", x=100, y=100, w=50, h=50),
            _el(id="deleted", x=0, y=0, w=1000, h=1000, isDeleted=True),
        ]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 100
        assert min_y == 100
        assert max_x == 150
        assert max_y == 150


class TestArrowAndLineBoundingBox:
    """Test bounding box with arrows and lines."""

    def test_arrow_with_points(self):
        elements = [
            _el(
                id="arrow1",
                type="arrow",
                x=100,
                y=100,
                w=200,
                h=0,
                points=[[0, 0], [200, 0]],
            ),
        ]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 100
        assert min_y == 100
        assert max_x == 300
        assert max_y == 100

    def test_line_with_points(self):
        elements = [
            _el(
                id="line1",
                type="line",
                x=0,
                y=0,
                w=0,
                h=100,
                points=[[0, 0], [0, 100]],
            ),
        ]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 0
        assert min_y == 0
        assert max_x == 0
        assert max_y == 100

    def test_arrow_with_negative_points(self):
        elements = [
            _el(
                id="arrow1",
                type="arrow",
                x=200,
                y=200,
                points=[[0, 0], [-100, -50]],
            ),
        ]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 100
        assert min_y == 150
        assert max_x == 200
        assert max_y == 200


class TestMalformedInput:
    """Test handling of malformed inputs (3.1, 3.2)."""

    def test_non_numeric_x(self, caplog):
        """Non-numeric x defaults to 0 with warning."""
        with caplog.at_level(logging.WARNING, logger="excalidraw_render"):
            elements = [_el(x="bad", y=100, w=50, h=50)]
            min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 0  # defaulted to 0
        assert any("non-numeric" in r.message.lower() for r in caplog.records)

    def test_none_coordinates(self, caplog):
        """None coordinates default to 0."""
        with caplog.at_level(logging.WARNING, logger="excalidraw_render"):
            elements = [
                {"id": "el1", "type": "rectangle", "x": None, "y": None, "width": 100, "height": 50}
            ]
            compute_bounding_box(elements)

    def test_malformed_points_skipped(self, caplog):
        """Malformed arrow points are skipped with warning (3.1)."""
        with caplog.at_level(logging.WARNING, logger="excalidraw_render"):
            elements = [
                _el(
                    id="arrow1",
                    type="arrow",
                    x=100,
                    y=100,
                    points=[[0, 0], [50], [100, 50]],  # middle point malformed
                ),
            ]
            min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        # Should still get valid bounds from the good points
        assert min_x == 100
        assert min_y == 100
        assert max_x == 200
        assert max_y == 150
        assert any("malformed point" in r.message.lower() for r in caplog.records)

    def test_non_numeric_points_skipped(self, caplog):
        """Non-numeric point values are skipped with warning (3.1)."""
        with caplog.at_level(logging.WARNING, logger="excalidraw_render"):
            elements = [
                _el(
                    id="arrow1",
                    type="arrow",
                    x=0,
                    y=0,
                    points=[[0, 0], ["x", "y"], [100, 100]],
                ),
            ]
            min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 0
        assert max_x == 100
        assert any("non-numeric point" in r.message.lower() for r in caplog.records)

    def test_non_dict_elements_skipped(self):
        """Non-dict elements are silently skipped."""
        elements = ["not a dict", 42, None, _el(x=10, y=20, w=30, h=40)]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert min_x == 10
        assert min_y == 20


class TestNegativeWidthHeight:
    """Test handling of negative width/height."""

    def test_negative_width_uses_abs(self):
        elements = [_el(x=100, y=100, w=-50, h=50)]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert max_x == 150  # 100 + abs(-50)
