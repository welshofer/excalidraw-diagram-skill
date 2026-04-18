"""Tests that validate all example .excalidraw files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from render_excalidraw import validate_excalidraw, compute_bounding_box

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


def _get_example_files():
    """Get all .excalidraw files in the examples directory."""
    if not EXAMPLES_DIR.exists():
        return []
    return sorted(EXAMPLES_DIR.glob("*.excalidraw"))


@pytest.mark.parametrize(
    "example_file",
    _get_example_files(),
    ids=lambda f: f.name,
)
class TestExampleFiles:
    """Validate all example .excalidraw files."""

    def test_valid_json(self, example_file):
        """Example file must be valid JSON."""
        raw = example_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict)

    def test_passes_validation(self, example_file):
        """Example file must pass validation."""
        raw = example_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        errors = validate_excalidraw(data)
        assert errors == [], f"Validation errors in {example_file.name}: {errors}"

    def test_has_elements(self, example_file):
        """Example file must have at least one element."""
        raw = example_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert len(data.get("elements", [])) > 0

    def test_bounding_box_reasonable(self, example_file):
        """Bounding box must be non-degenerate."""
        raw = example_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        elements = [e for e in data["elements"] if not e.get("isDeleted")]
        min_x, min_y, max_x, max_y = compute_bounding_box(elements)
        assert max_x > min_x, "Degenerate bounding box (zero width)"
        assert max_y > min_y or any(
            e.get("type") in ("line", "arrow") for e in elements
        ), "Degenerate bounding box (zero height)"
