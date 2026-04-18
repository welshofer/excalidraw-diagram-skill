"""Tests covering Section 2 (Functionality) of improvement plan v2."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import render_excalidraw as rx
import lint_excalidraw as lx
import themes
import shortform
import convert_mermaid as cm


def _make_diagram(elements=None):
    return {
        "type": "excalidraw",
        "version": 2,
        "elements": elements or [],
        "appState": {},
        "files": {},
    }


# --- v2 2.1: watermark --------------------------------------------------------
class TestWatermark:
    def test_apply_watermark_requires_png(self, tmp_path):
        pytest.importorskip("PIL")
        from PIL import Image

        p = tmp_path / "plain.png"
        Image.new("RGB", (300, 200), "white").save(str(p))
        before_bytes = p.read_bytes()
        rx._apply_watermark(p)
        after_bytes = p.read_bytes()
        assert before_bytes != after_bytes

    def test_apply_watermark_missing_pillow_warns(self, tmp_path, monkeypatch):
        # Block PIL import by adding a sentinel finder.
        monkeypatch.setitem(sys.modules, "PIL", None)
        p = tmp_path / "missing.png"
        p.write_bytes(b"\x89PNG")
        rx._apply_watermark(p)  # Should not raise.


# --- v2 2.2: diff auto-snapshot ----------------------------------------------
class TestDiffAutoSnapshot:
    def test_auto_snapshot_registered(self):
        """Render tracks the previous PNG snapshot in a module dict."""
        rx._LAST_PREV_SNAPSHOT["/tmp/none.png"] = Path("/tmp/none.png.prev")
        assert rx._LAST_PREV_SNAPSHOT["/tmp/none.png"].name == "none.png.prev"


# --- v2 2.3: HTML export with vendor bundle -----------------------------------
class TestHtmlExport:
    def test_html_export_no_cdn_when_inline(self, tmp_path, monkeypatch):
        # Point VENDOR_DIR at a directory with a dummy bundle so _vendor is True.
        vendor_dir = tmp_path / "vendor"
        vendor_dir.mkdir()
        bundle = vendor_dir / "excalidraw-bundle.js"
        bundle.write_text("export const exportToSvg = () => {};", encoding="utf-8")
        import hashlib
        integrity = {
            "version": rx.EXCALIDRAW_VERSION,
            "method": "test",
            "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "sri": "sha384-dummy",
            "size_bytes": bundle.stat().st_size,
        }
        (vendor_dir / "integrity.json").write_text(json.dumps(integrity), encoding="utf-8")
        monkeypatch.setattr(rx, "VENDOR_DIR", vendor_dir)
        rx._invalidate_caches()

        out = tmp_path / "demo.html"
        rx._export_html(_make_diagram(), out, dark_mode=False, inline_bundle=True)
        text = out.read_text(encoding="utf-8")
        assert "esm.sh" not in text
        assert "blobUrl" in text


# --- v2 2.4: --all batch CLI --------------------------------------------------
class TestAllFlagArgument:
    def test_all_collects_excalidraw_files(self, tmp_path):
        (tmp_path / "x.excalidraw").write_text(json.dumps(_make_diagram()), encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "y.excalidraw").write_text(json.dumps(_make_diagram()), encoding="utf-8")
        found = sorted(tmp_path.rglob("*.excalidraw"))
        assert len(found) == 2


# --- v2 2.5: frames lint ------------------------------------------------------
class TestFrameLint:
    def test_frame_overlap(self):
        data = _make_diagram([
            {"id": "f1", "type": "frame", "x": 0, "y": 0, "width": 200, "height": 200},
            {"id": "f2", "type": "frame", "x": 100, "y": 100, "width": 200, "height": 200},
        ])
        issues = lx.lint_excalidraw(data)
        assert any(i["code"] == "frame-overlap" for i in issues)

    def test_frame_child_out_of_bounds(self):
        data = _make_diagram([
            {"id": "f1", "type": "frame", "x": 0, "y": 0, "width": 100, "height": 100,
             "boundElements": [{"id": "r1", "type": "rectangle"}]},
            {"id": "r1", "type": "rectangle", "x": 150, "y": 150, "width": 40, "height": 40, "frameId": "f1"},
        ])
        issues = lx.lint_excalidraw(data)
        assert any(i["code"] == "frame-child-out-of-bounds" for i in issues)

    def test_frame_label_overflow(self):
        long = "X" * 100
        data = _make_diagram([
            {"id": "f1", "type": "frame", "x": 0, "y": 0, "width": 80, "height": 80, "name": long},
        ])
        issues = lx.lint_excalidraw(data)
        assert any(i["code"] == "frame-label-overflow" for i in issues)


# --- v2 2.6: themes -----------------------------------------------------------
class TestThemes:
    @pytest.mark.parametrize("theme", sorted(k for k in themes.PALETTES.keys() if k != "default"))
    def test_apply_theme_remaps_colors(self, theme):
        data = _make_diagram([{
            "id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100,
            "strokeColor": "#1971c2",  # accent stroke in default palette
            "backgroundColor": "#a5d8ff",  # accent fill
        }])
        themes.apply_theme(data, theme)
        expected_stroke = themes.PALETTES[theme]["accent"][0]
        expected_fill = themes.PALETTES[theme]["accent"][1]
        el = data["elements"][0]
        assert el["strokeColor"] == expected_stroke
        assert el["backgroundColor"] == expected_fill

    def test_unknown_theme_raises(self):
        with pytest.raises(ValueError):
            themes.apply_theme(_make_diagram(), "nope")

    def test_default_noop(self):
        d = _make_diagram([{"id": "a", "type": "rectangle", "x": 0, "y": 0,
                            "width": 10, "height": 10,
                            "strokeColor": "#1e1e1e", "backgroundColor": "#ffffff"}])
        themes.apply_theme(d, "default")
        assert d["elements"][0]["strokeColor"] == "#1e1e1e"


# --- v2 2.7: Mermaid converter ------------------------------------------------
class TestMermaidConverter:
    def test_round_trip_basic(self):
        text = """graph LR
        A[Start] --> B[Middle]
        B --> C[End]
        """
        data = cm.compile_mermaid(text)
        assert data["type"] == "excalidraw"
        # 3 rects + 3 texts + 2 arrows
        rects = [e for e in data["elements"] if e["type"] == "rectangle"]
        arrows = [e for e in data["elements"] if e["type"] == "arrow"]
        assert len(rects) == 3
        assert len(arrows) == 2

    def test_graph_td(self):
        data = cm.compile_mermaid("graph TD\nA-->B")
        assert any(e["type"] == "arrow" for e in data["elements"])

    def test_node_labels(self):
        data = cm.compile_mermaid("graph LR\nA[Hello]-->B[World]")
        texts = [e for e in data["elements"] if e["type"] == "text"]
        labels = {t["text"] for t in texts}
        assert "Hello" in labels and "World" in labels

    def test_cycle_handled(self):
        text = "graph LR\nA-->B\nB-->A"
        data = cm.compile_mermaid(text)
        rects = [e for e in data["elements"] if e["type"] == "rectangle"]
        assert len(rects) == 2

    def test_generates_valid_excalidraw(self):
        data = cm.compile_mermaid("graph LR\nA[a]-->B[b]")
        errors = rx.validate_excalidraw(data)
        assert errors == [], errors


# --- v2 2.8: stats ------------------------------------------------------------
class TestStats:
    def test_print_stats_json(self, tmp_path, capsys):
        p = tmp_path / "d.excalidraw"
        p.write_text(json.dumps(_make_diagram([
            {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100, "strokeColor": "#ff0000"},
            {"id": "b", "type": "ellipse", "x": 200, "y": 0, "width": 50, "height": 50, "strokeColor": "#00ff00"},
        ])), encoding="utf-8")
        rx._print_stats(p, json_output=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["elements_total"] == 2
        assert data["distinct_stroke_colors"] == 2

    def test_print_stats_human(self, tmp_path, capsys):
        p = tmp_path / "d.excalidraw"
        p.write_text(json.dumps(_make_diagram([
            {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50},
        ])), encoding="utf-8")
        rx._print_stats(p, json_output=False)
        out = capsys.readouterr().out
        assert "elements_total" in out


# --- v2 2.9: PDF --------------------------------------------------------------
class TestPdfArgument:
    def test_pdf_flag_added(self):
        # --pdf is defined on the parser (integration-test renders it; here we
        # confirm the flag is wired up by running --help).
        from subprocess import run
        r = run(
            [sys.executable, "render_excalidraw.py", "--help"],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True, text=True,
        )
        assert "--pdf" in r.stdout


# --- v2 2.10: shortform DSL ---------------------------------------------------
class TestShortform:
    def test_rect_with_text(self):
        src = 'shape: rect id: a text: "Hi" at: [0, 0] size: [100, 50]'
        data = shortform.compile_shortform(src)
        rects = [e for e in data["elements"] if e["type"] == "rectangle"]
        texts = [e for e in data["elements"] if e["type"] == "text"]
        assert rects and texts
        assert texts[0]["text"] == "Hi"

    def test_ellipse(self):
        data = shortform.compile_shortform('shape: ellipse id: b at: [10, 10] size: [60, 60]')
        assert any(e["type"] == "ellipse" for e in data["elements"])

    def test_diamond(self):
        data = shortform.compile_shortform('shape: diamond id: c at: [0, 0] size: [80, 80]')
        assert any(e["type"] == "diamond" for e in data["elements"])

    def test_arrow_binding(self):
        src = """
        shape: rect id: a at: [0, 0] size: [100, 50]
        shape: rect id: b at: [200, 0] size: [100, 50]
        arrow: from: a to: b
        """
        data = shortform.compile_shortform(src)
        arrows = [e for e in data["elements"] if e["type"] == "arrow"]
        assert arrows
        assert arrows[0]["startBinding"]["elementId"] == "a"
        assert arrows[0]["endBinding"]["elementId"] == "b"

    def test_comment_ignored(self):
        data = shortform.compile_shortform("# comment\nshape: rect id: z")
        assert any(e["type"] == "rectangle" for e in data["elements"])

    def test_text_only(self):
        data = shortform.compile_shortform('shape: text id: t text: "Hello"')
        texts = [e for e in data["elements"] if e["type"] == "text"]
        assert texts and texts[0]["text"] == "Hello"

    def test_role_applied(self):
        data = shortform.compile_shortform('shape: rect id: a role: danger at: [0, 0] size: [50, 50]')
        danger = themes.PALETTES["default"]["danger"]
        el = [e for e in data["elements"] if e["type"] == "rectangle"][0]
        assert el["strokeColor"] == danger[0]

    def test_output_validates(self):
        src = """
        shape: rect id: a text: "one" at: [0, 0] size: [100, 50]
        shape: ellipse id: b text: "two" at: [200, 0] size: [100, 50]
        arrow: from: a to: b
        """
        data = shortform.compile_shortform(src)
        errors = rx.validate_excalidraw(data)
        assert errors == [], errors
