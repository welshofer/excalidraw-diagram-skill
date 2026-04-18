"""Tests for validate_excalidraw() function."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent directory to path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from render_excalidraw import validate_excalidraw


def _make_diagram(elements=None, type_field="excalidraw"):
    """Helper to create a minimal valid diagram dict."""
    d = {"type": type_field, "version": 2, "elements": elements or [], "appState": {}, "files": {}}
    return d


def _make_element(id="el1", type="rectangle", x=0, y=0, w=100, h=50, **kwargs):
    """Helper to create a minimal element dict."""
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


class TestTopLevelValidation:
    """Test top-level structure validation."""

    def test_valid_minimal(self):
        data = _make_diagram([_make_element()])
        errors = validate_excalidraw(data)
        assert errors == []

    def test_wrong_type(self):
        data = _make_diagram([_make_element()], type_field="not_excalidraw")
        errors = validate_excalidraw(data)
        assert len(errors) == 1
        assert "Expected type 'excalidraw'" in errors[0]

    def test_missing_elements(self):
        data = {"type": "excalidraw", "version": 2}
        errors = validate_excalidraw(data)
        assert any("Missing 'elements' array" in e for e in errors)

    def test_elements_not_array(self):
        data = {"type": "excalidraw", "elements": "not_an_array"}
        errors = validate_excalidraw(data)
        assert any("must be an array" in e for e in errors)

    def test_elements_empty(self):
        data = _make_diagram([])
        errors = validate_excalidraw(data)
        assert any("empty" in e for e in errors)


class TestElementValidation:
    """Test element-level validation."""

    def test_missing_id(self):
        el = {"type": "rectangle", "x": 0, "y": 0}
        data = _make_diagram([el])
        errors = validate_excalidraw(data)
        assert any("missing required field 'id'" in e for e in errors)

    def test_missing_type(self):
        el = {"id": "el1", "x": 0, "y": 0}
        data = _make_diagram([el])
        errors = validate_excalidraw(data)
        assert any("missing required field 'type'" in e for e in errors)

    def test_non_numeric_coordinates(self):
        el = _make_element(x="not_a_number")
        data = _make_diagram([el])
        errors = validate_excalidraw(data)
        assert any("non-numeric 'x'" in e for e in errors)

    def test_duplicate_ids(self):
        el1 = _make_element(id="dup")
        el2 = _make_element(id="dup", type="ellipse")
        data = _make_diagram([el1, el2])
        errors = validate_excalidraw(data)
        assert any("Duplicate element ID 'dup'" in e for e in errors)

    def test_element_not_dict(self):
        data = _make_diagram(["not_a_dict"])
        errors = validate_excalidraw(data)
        assert any("not an object" in e for e in errors)


class TestBindingValidation:
    """Test cross-reference and binding integrity."""

    def test_valid_bindings(self):
        rect = _make_element(id="rect1", boundElements=[{"id": "text1", "type": "text"}])
        text = _make_element(id="text1", type="text", containerId="rect1")
        data = _make_diagram([rect, text])
        errors = validate_excalidraw(data)
        assert errors == []

    def test_arrow_binding_to_nonexistent(self):
        arrow = _make_element(
            id="arrow1", type="arrow",
            startBinding={"elementId": "nonexistent", "focus": 0, "gap": 2},
            points=[[0, 0], [100, 0]],
        )
        data = _make_diagram([arrow])
        errors = validate_excalidraw(data)
        assert any("non-existent element 'nonexistent'" in e for e in errors)

    def test_container_id_nonexistent(self):
        text = _make_element(id="text1", type="text", containerId="missing_rect")
        data = _make_diagram([text])
        errors = validate_excalidraw(data)
        assert any("non-existent element 'missing_rect'" in e for e in errors)


class TestSecurityValidation:
    """Test security-related validation."""

    def test_dangerous_link_javascript(self):
        el = _make_element(link="javascript:alert('xss')")
        data = _make_diagram([el])
        errors = validate_excalidraw(data)
        assert any("dangerous link" in e.lower() for e in errors)

    def test_dangerous_link_data(self):
        el = _make_element(link="data:text/html,<script>alert(1)</script>")
        data = _make_diagram([el])
        errors = validate_excalidraw(data)
        assert any("dangerous link" in e.lower() for e in errors)

    def test_safe_link_https(self):
        el = _make_element(link="https://example.com")
        data = _make_diagram([el])
        errors = validate_excalidraw(data)
        assert errors == []

    def test_element_count_limit(self):
        elements = [_make_element(id=f"el{i}") for i in range(100)]
        data = _make_diagram(elements)
        errors = validate_excalidraw(data, max_elements=50)
        assert any("exceeds limit" in e for e in errors)


class TestSeedValidation:
    """Test seed value validation (5.7)."""

    def test_negative_seed_warns(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="excalidraw_render"):
            el = _make_element(seed=-1)
            data = _make_diagram([el])
            validate_excalidraw(data)
        assert any("negative" in r.message.lower() for r in caplog.records)

    def test_huge_seed_warns(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="excalidraw_render"):
            el = _make_element(seed=2**54)
            data = _make_diagram([el])
            validate_excalidraw(data)
        assert any("MAX_SAFE_INTEGER" in r.message for r in caplog.records)
