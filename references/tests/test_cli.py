"""Tests for CLI argument parsing and rendering pipeline."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from render_excalidraw import (
    RenderError,
    validate_path,
    _check_cache,
    _write_cache,
    _generate_excalidraw_url,
    _export_html,
    FORMAT_PRESETS,
)


class TestPathValidation:
    """Test path validation (5.3)."""

    def test_valid_png_output(self):
        errors = validate_path(Path("/tmp/output.png"), kind="output")
        assert errors == []

    def test_valid_svg_output(self):
        errors = validate_path(Path("/tmp/output.svg"), kind="output")
        assert errors == []

    def test_invalid_output_extension(self):
        errors = validate_path(Path("/tmp/output.txt"), kind="output")
        assert len(errors) > 0
        assert "extension" in errors[0].lower()

    def test_system_dir_blocked(self):
        errors = validate_path(Path("/etc/evil.png"), kind="output")
        assert len(errors) > 0
        assert "system directory" in errors[0].lower()


class TestCache:
    """Test render caching (4.6)."""

    def test_cache_miss_no_hash_file(self):
        with tempfile.NamedTemporaryFile(suffix=".excalidraw") as f:
            excalidraw_path = Path(f.name)
            output_path = excalidraw_path.with_suffix(".png")
            assert not _check_cache(excalidraw_path, output_path, "test content")

    def test_cache_write_and_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            excalidraw_path = Path(tmpdir) / "test.excalidraw"
            output_path = Path(tmpdir) / "test.png"

            raw = '{"test": "content"}'
            excalidraw_path.write_text(raw)
            output_path.write_text("fake png")

            _write_cache(excalidraw_path, raw)
            assert _check_cache(excalidraw_path, output_path, raw)

    def test_cache_miss_on_content_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            excalidraw_path = Path(tmpdir) / "test.excalidraw"
            output_path = Path(tmpdir) / "test.png"

            raw1 = '{"test": "content1"}'
            excalidraw_path.write_text(raw1)
            output_path.write_text("fake png")
            _write_cache(excalidraw_path, raw1)

            raw2 = '{"test": "content2"}'
            assert not _check_cache(excalidraw_path, output_path, raw2)


class TestExcalidrawUrl:
    """Test URL generation (2.9)."""

    def test_generates_url(self):
        data = {"type": "excalidraw", "elements": [], "appState": {}}
        url = _generate_excalidraw_url(data)
        assert url.startswith("https://excalidraw.com/#json=")

    def test_url_contains_encoded_data(self):
        data = {"type": "excalidraw", "elements": [{"id": "test"}]}
        url = _generate_excalidraw_url(data)
        # Should be base64url encoded
        encoded_part = url.split("#json=")[1]
        assert len(encoded_part) > 0


class TestHtmlExport:
    """Test HTML export (7.10)."""

    def test_creates_html_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.html"
            data = {"type": "excalidraw", "elements": [], "appState": {}}
            _export_html(data, output)
            assert output.exists()
            content = output.read_text()
            assert "excalidraw" in content
            assert "exportToSvg" in content

    def test_dark_mode_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "dark.html"
            data = {"type": "excalidraw", "elements": [], "appState": {}}
            _export_html(data, output, dark_mode=True)
            content = output.read_text()
            assert "#1e1e1e" in content


class TestFormatPresets:
    """Test format presets (6.9)."""

    def test_all_presets_have_required_keys(self):
        for name, preset in FORMAT_PRESETS.items():
            assert "width" in preset, f"Preset {name} missing 'width'"
            assert "scale" in preset, f"Preset {name} missing 'scale'"

    def test_presentation_preset(self):
        assert FORMAT_PRESETS["presentation"]["width"] == 1920

    def test_thumbnail_preset(self):
        assert FORMAT_PRESETS["thumbnail"]["width"] == 400
        assert FORMAT_PRESETS["thumbnail"]["scale"] == 1


class TestRenderError:
    """Test RenderError exception."""

    def test_render_error_is_exception(self):
        with pytest.raises(RenderError):
            raise RenderError("test error")

    def test_render_error_message(self):
        try:
            raise RenderError("test message")
        except RenderError as e:
            assert str(e) == "test message"


class TestFileValidation:
    """Test file size and input validation."""

    def test_render_rejects_missing_file(self):
        from render_excalidraw import render
        with pytest.raises((RenderError, SystemExit)):
            render(Path("/nonexistent/file.excalidraw"))

    def test_render_rejects_invalid_json(self):
        from render_excalidraw import render
        with tempfile.NamedTemporaryFile(suffix=".excalidraw", mode="w", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()
            with pytest.raises(RenderError, match="Invalid JSON"):
                render(Path(f.name))

    def test_render_rejects_invalid_structure(self):
        from render_excalidraw import render
        with tempfile.NamedTemporaryFile(suffix=".excalidraw", mode="w", delete=False) as f:
            json.dump({"type": "not_excalidraw"}, f)
            f.flush()
            with pytest.raises(RenderError, match="Invalid Excalidraw"):
                render(Path(f.name))
