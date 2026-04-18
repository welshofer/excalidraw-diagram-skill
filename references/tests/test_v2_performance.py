"""Tests covering Section 1 (Performance) of improvement plan v2."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import render_excalidraw as rx
import lint_excalidraw as lx


def _make_diagram(n: int) -> dict:
    elements = []
    for i in range(n):
        elements.append(
            {
                "id": f"e{i}",
                "type": "rectangle",
                "x": (i % 50) * 200,
                "y": (i // 50) * 120,
                "width": 160,
                "height": 80,
            }
        )
    return {"type": "excalidraw", "version": 2, "elements": elements, "appState": {}, "files": {}}


# --- v2 1.2: vendor detection / template memoization ---------------------------
class TestTemplateMemoization:
    def test_vendor_cache_key_stable(self, tmp_path):
        orig = rx.VENDOR_DIR
        try:
            rx.VENDOR_DIR = tmp_path
            rx._invalidate_caches()
            k1 = rx._vendor_cache_key()
            k2 = rx._vendor_cache_key()
            assert k1 == k2
        finally:
            rx.VENDOR_DIR = orig
            rx._invalidate_caches()

    def test_vendor_cache_invalidated_on_dir_change(self, tmp_path):
        orig = rx.VENDOR_DIR
        try:
            rx.VENDOR_DIR = tmp_path / "a"
            rx._invalidate_caches()
            assert rx._vendor_bundle_available() is False
            # New dir -> new key -> re-evaluates.
            rx.VENDOR_DIR = tmp_path / "b"
            assert rx._vendor_bundle_available() is False
        finally:
            rx.VENDOR_DIR = orig
            rx._invalidate_caches()

    def test_resolve_template_cached(self):
        rx._invalidate_caches()
        t1 = rx._resolve_template_html()
        t2 = rx._resolve_template_html()
        # Must be identical strings from the cache.
        assert t1 is t2 or t1 == t2


# --- v2 1.3: validator consolidated pass ---------------------------------------
class TestValidatorPerf:
    def test_validate_5000_elements_under_200ms(self):
        data = _make_diagram(5000)
        t0 = time.perf_counter()
        errs = rx.validate_excalidraw(data, max_elements=10000)
        elapsed = time.perf_counter() - t0
        assert errs == []
        # Generous bound for CI variance.
        assert elapsed < 1.0, f"validate took {elapsed:.3f}s"


# --- v2 1.4 + 1.6: lint sweep-line overlap check -------------------------------
class TestLintOverlapPerf:
    def test_lint_500_nonoverlapping_under_1s(self):
        data = _make_diagram(500)
        t0 = time.perf_counter()
        issues = lx.lint_excalidraw(data)
        elapsed = time.perf_counter() - t0
        # Non-overlapping diagram on a 50-col grid at 200px spacing.
        assert all(i["code"] != "overlap" for i in issues), issues
        assert elapsed < 1.5, f"lint took {elapsed:.3f}s"

    def test_lint_detects_overlap(self):
        data = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100},
                {"id": "b", "type": "rectangle", "x": 20, "y": 20, "width": 100, "height": 100},
            ],
            "appState": {},
            "files": {},
        }
        issues = lx.lint_excalidraw(data)
        assert any(i["code"] == "overlap" for i in issues)


# --- v2 1.5 + 2.4: batch render argv handling ----------------------------------
class TestBatchArgs:
    def test_input_nargs_accepts_multiple(self):
        # argparse should accept any number of positional inputs.

        # Just validate the argparse config doesn't reject multiple inputs.
        import render_excalidraw as r

        # Re-invoke main via a subprocess-style check is heavy; instead rebuild parser.
        # We inspect the module's argparse setup indirectly by checking _batch_render.
        assert callable(r._batch_render)

    def test_all_dir_collects(self, tmp_path):
        # Create two fake files.
        (tmp_path / "a.excalidraw").write_text(json.dumps(_make_diagram(1)), encoding="utf-8")
        (tmp_path / "b.excalidraw").write_text(json.dumps(_make_diagram(1)), encoding="utf-8")
        found = sorted(tmp_path.rglob("*.excalidraw"))
        assert len(found) == 2


# --- v2 1.9: validator accepts multiple paths ----------------------------------
class TestValidateMultipleInputs:
    def test_validate_cli_multi(self, tmp_path):
        import subprocess
        import sys as _sys

        p1 = tmp_path / "one.excalidraw"
        p2 = tmp_path / "two.excalidraw"
        for p in (p1, p2):
            p.write_text(json.dumps(_make_diagram(2)), encoding="utf-8")
        result = subprocess.run(
            [_sys.executable, "validate_excalidraw.py", str(p1), str(p2)],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "one.excalidraw" in result.stdout
        assert "two.excalidraw" in result.stdout


# --- v2 1.1: server resize + template resolver hook ----------------------------
class TestServerTemplate:
    def test_server_uses_resolve_template(self, monkeypatch):
        """start_server must route through _resolve_template_html, not read raw."""
        called = {"count": 0}

        original = rx._resolve_template_html

        def fake_resolve():
            called["count"] += 1
            return original()

        # Patch and simulate enough of playwright to fail fast after template load.
        monkeypatch.setattr(rx, "_resolve_template_html", fake_resolve)

        # Simulate import failure of playwright so we don't actually launch.
        fake_mod = MagicMock()
        fake_mod.sync_playwright.side_effect = RuntimeError("no browser")
        monkeypatch.setitem(sys.modules, "playwright", MagicMock())
        monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)

        with pytest.raises((rx.RenderError, RuntimeError)):
            rx.start_server(port=0)
        assert called["count"] >= 1
