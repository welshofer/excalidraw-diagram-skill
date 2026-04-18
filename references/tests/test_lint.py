"""Tests for lint_excalidraw.py (2.4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lint_excalidraw import (
    lint_excalidraw,
    auto_fix,
    _estimate_text_width,
    _get_element_bbox,
    _boxes_overlap,
)


def _make_diagram(elements=None):
    return {
        "type": "excalidraw",
        "version": 2,
        "elements": elements or [],
        "appState": {},
        "files": {},
    }


def _make_element(id="el1", type="rectangle", x=0, y=0, w=100, h=50, **kwargs):
    el = {
        "id": id,
        "type": type,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "seed": 12345,
        "versionNonce": 67890,
    }
    el.update(kwargs)
    return el


class TestTextWidthEstimation:
    """Test text width estimation."""

    def test_monospace_width(self):
        w = _estimate_text_width("Hello", 16, font_family=3)
        # 5 chars * 16 * 0.60 = 48
        assert w == pytest.approx(48.0)

    def test_multiline_uses_longest(self):
        w = _estimate_text_width("Hi\nHello World", 16, font_family=3)
        # "Hello World" = 11 chars * 16 * 0.60 = 105.6
        assert w == pytest.approx(11 * 16 * 0.60)

    def test_empty_text(self):
        w = _estimate_text_width("", 16)
        assert w == 0.0

    def test_default_factor_for_unknown_font(self):
        w = _estimate_text_width("AB", 10, font_family=99)
        assert w == pytest.approx(2 * 10 * 0.55)


class TestElementBbox:
    """Test element bounding box computation."""

    def test_rectangle_bbox(self):
        el = _make_element(x=100, y=200, w=300, h=150)
        bbox = _get_element_bbox(el)
        assert bbox == (100, 200, 400, 350)

    def test_deleted_element_returns_none(self):
        el = _make_element(isDeleted=True)
        assert _get_element_bbox(el) is None

    def test_arrow_with_points(self):
        el = _make_element(
            type="arrow",
            x=100,
            y=100,
            w=200,
            h=0,
            points=[[0, 0], [200, 50]],
        )
        bbox = _get_element_bbox(el)
        assert bbox == (100, 100, 300, 150)

    def test_non_dict_returns_none(self):
        assert _get_element_bbox("not a dict") is None


class TestBoxOverlap:
    """Test overlap detection."""

    def test_no_overlap(self):
        a = (0, 0, 100, 100)
        b = (200, 200, 300, 300)
        assert not _boxes_overlap(a, b)

    def test_full_overlap(self):
        a = (0, 0, 100, 100)
        b = (10, 10, 90, 90)
        assert _boxes_overlap(a, b)

    def test_partial_overlap_below_threshold(self):
        a = (0, 0, 100, 100)
        b = (90, 90, 200, 200)
        # Overlap area = 10*10 = 100, smaller area = 100*100 = 10000
        # 100/10000 = 0.01 < 0.3 threshold
        assert not _boxes_overlap(a, b)

    def test_significant_overlap(self):
        a = (0, 0, 100, 100)
        b = (20, 20, 120, 120)
        # Overlap = 80*80 = 6400, smaller area = 10000
        # 6400/10000 = 0.64 > 0.3
        assert _boxes_overlap(a, b)


class TestLintOverlap:
    """Test overlap detection in lint."""

    def test_overlapping_rectangles_detected(self):
        r1 = _make_element(id="r1", x=0, y=0, w=100, h=100)
        r2 = _make_element(id="r2", x=20, y=20, w=100, h=100)
        data = _make_diagram([r1, r2])
        issues = lint_excalidraw(data)
        overlap_issues = [i for i in issues if i["code"] == "overlap"]
        assert len(overlap_issues) >= 1

    def test_non_overlapping_no_issue(self):
        r1 = _make_element(id="r1", x=0, y=0, w=100, h=50)
        r2 = _make_element(id="r2", x=200, y=0, w=100, h=50)
        data = _make_diagram([r1, r2])
        issues = lint_excalidraw(data)
        overlap_issues = [i for i in issues if i["code"] == "overlap"]
        assert len(overlap_issues) == 0

    def test_bound_text_container_not_flagged(self):
        rect = _make_element(
            id="rect1",
            x=0,
            y=0,
            w=200,
            h=100,
            boundElements=[{"id": "text1", "type": "text"}],
        )
        # Text is the same shape type as container for bbox overlap,
        # but since it's a text type, the overlap check only checks shape_types
        data = _make_diagram([rect])
        issues = lint_excalidraw(data)
        overlap_issues = [i for i in issues if i["code"] == "overlap"]
        assert len(overlap_issues) == 0


class TestLintTextOverflow:
    """Test text overflow detection."""

    def test_text_overflows_small_container(self):
        container = _make_element(
            id="box1",
            type="rectangle",
            x=0,
            y=0,
            w=60,
            h=40,
            boundElements=[{"id": "txt1", "type": "text"}],
        )
        text = _make_element(
            id="txt1",
            type="text",
            x=5,
            y=5,
            w=50,
            h=20,
            text="This is a very long text that overflows",
            originalText="This is a very long text that overflows",
            fontSize=16,
            fontFamily=3,
            containerId="box1",
        )
        data = _make_diagram([container, text])
        issues = lint_excalidraw(data)
        overflow_issues = [i for i in issues if i["code"] == "text-overflow"]
        assert len(overflow_issues) >= 1
        # Should have a fix suggestion
        assert overflow_issues[0].get("fix") is not None
        assert overflow_issues[0]["fix"]["action"] == "widen_container"

    def test_text_fits_container(self):
        container = _make_element(
            id="box1",
            type="rectangle",
            x=0,
            y=0,
            w=300,
            h=50,
            boundElements=[{"id": "txt1", "type": "text"}],
        )
        text = _make_element(
            id="txt1",
            type="text",
            x=5,
            y=5,
            w=50,
            h=20,
            text="OK",
            originalText="OK",
            fontSize=14,
            fontFamily=3,
            containerId="box1",
        )
        data = _make_diagram([container, text])
        issues = lint_excalidraw(data)
        overflow_issues = [i for i in issues if i["code"] == "text-overflow"]
        assert len(overflow_issues) == 0

    def test_diamond_has_reduced_usable_width(self):
        diamond = _make_element(
            id="d1",
            type="diamond",
            x=0,
            y=0,
            w=140,
            h=100,
            boundElements=[{"id": "dt1", "type": "text"}],
        )
        text = _make_element(
            id="dt1",
            type="text",
            x=10,
            y=10,
            w=100,
            h=20,
            text="Long Decision Text Here",
            originalText="Long Decision Text Here",
            fontSize=14,
            fontFamily=3,
            containerId="d1",
        )
        data = _make_diagram([diamond, text])
        issues = lint_excalidraw(data)
        overflow_issues = [i for i in issues if i["code"] == "text-overflow"]
        # With diamond usable factor 0.55, usable width is small
        assert len(overflow_issues) >= 1


class TestLintIdenticalCoords:
    """Test identical coordinates detection."""

    def test_identical_positions_detected(self):
        r1 = _make_element(id="r1", x=100, y=100, w=50, h=50)
        r2 = _make_element(id="r2", x=100, y=100, w=80, h=80)
        data = _make_diagram([r1, r2])
        issues = lint_excalidraw(data)
        coord_issues = [i for i in issues if i["code"] == "identical-coords"]
        assert len(coord_issues) >= 1

    def test_different_positions_no_issue(self):
        r1 = _make_element(id="r1", x=0, y=0, w=50, h=50)
        r2 = _make_element(id="r2", x=200, y=200, w=50, h=50)
        data = _make_diagram([r1, r2])
        issues = lint_excalidraw(data)
        coord_issues = [i for i in issues if i["code"] == "identical-coords"]
        assert len(coord_issues) == 0


class TestLintUnboundArrow:
    """Test unbound arrow detection."""

    def test_unbound_arrow_detected(self):
        arrow = _make_element(
            id="arrow1",
            type="arrow",
            x=0,
            y=0,
            w=100,
            h=0,
            points=[[0, 0], [100, 0]],
        )
        data = _make_diagram([arrow])
        issues = lint_excalidraw(data)
        unbound = [i for i in issues if i["code"] == "unbound-arrow"]
        assert len(unbound) == 1

    def test_bound_arrow_not_flagged(self):
        rect = _make_element(id="r1", x=0, y=0, w=50, h=50)
        arrow = _make_element(
            id="arrow1",
            type="arrow",
            x=50,
            y=25,
            w=100,
            h=0,
            points=[[0, 0], [100, 0]],
            startBinding={"elementId": "r1", "focus": 0, "gap": 2},
        )
        data = _make_diagram([rect, arrow])
        issues = lint_excalidraw(data)
        unbound = [i for i in issues if i["code"] == "unbound-arrow"]
        assert len(unbound) == 0


class TestAutoFix:
    """Test auto-fix functionality."""

    def test_widen_container_fix(self):
        container = _make_element(
            id="box1",
            type="rectangle",
            x=0,
            y=0,
            w=60,
            h=40,
            boundElements=[{"id": "txt1", "type": "text"}],
        )
        text = _make_element(
            id="txt1",
            type="text",
            x=5,
            y=5,
            w=50,
            h=20,
            text="This is a very long text that definitely overflows",
            originalText="This is a very long text that definitely overflows",
            fontSize=16,
            fontFamily=3,
            containerId="box1",
        )
        data = _make_diagram([container, text])
        issues = lint_excalidraw(data)
        fixable = [i for i in issues if i.get("fix")]
        assert len(fixable) >= 1

        fixed = auto_fix(data, issues)
        # Container should be wider now
        fixed_elements = {e["id"]: e for e in fixed["elements"]}
        assert fixed_elements["box1"]["width"] > 60

    def test_autofix_doesnt_modify_original(self):
        container = _make_element(
            id="box1",
            type="rectangle",
            x=0,
            y=0,
            w=60,
            h=40,
            boundElements=[{"id": "txt1", "type": "text"}],
        )
        text = _make_element(
            id="txt1",
            type="text",
            x=5,
            y=5,
            w=50,
            h=20,
            text="Overflow text here please",
            originalText="Overflow text here please",
            fontSize=16,
            fontFamily=3,
            containerId="box1",
        )
        data = _make_diagram([container, text])
        original_width = data["elements"][0]["width"]
        issues = lint_excalidraw(data)
        auto_fix(data, issues)
        # Original should be unchanged
        assert data["elements"][0]["width"] == original_width


class TestLintEmptyDiagram:
    """Edge cases."""

    def test_empty_elements(self):
        data = _make_diagram([])
        issues = lint_excalidraw(data)
        assert issues == []

    def test_non_list_elements(self):
        data = {"type": "excalidraw", "elements": "not_a_list"}
        issues = lint_excalidraw(data)
        assert issues == []

    def test_all_deleted_elements(self):
        el = _make_element(isDeleted=True)
        data = _make_diagram([el])
        issues = lint_excalidraw(data)
        assert issues == []
