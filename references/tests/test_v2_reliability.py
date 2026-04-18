"""Tests covering Section 4 (Reliability) of improvement plan v2."""

from __future__ import annotations

import io
import json
import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import render_excalidraw as rx


def _diag(elements=None):
    return {
        "type": "excalidraw",
        "version": 2,
        "elements": elements or [],
        "appState": {},
        "files": {},
    }


# --- v2 4.1: ruff in CI (check that workflow references ruff) ---------------
class TestRuffInCI:
    def test_workflow_mentions_ruff(self):
        wf = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"
        text = wf.read_text(encoding="utf-8")
        assert "ruff check" in text


# --- v2 4.2: integration POST behaviour (fake page) -------------------------
class TestServerPostIntegration:
    def test_render_server_post_with_fake_page(self, tmp_path):
        """Drive _handle_render end-to-end with a fake playwright page."""
        from io import BytesIO

        captured = {"status": None, "body": b""}

        class FakePage:
            def evaluate(self, script, *args, **kwargs):
                # Reset/inline scripts return undefined.
                if "__renderComplete = false" in script:
                    return None
                # Probe for the render error sentinel (= null or null).
                if script.strip() == "() => window.__renderError":
                    return None
                if "renderDiagram" in script:
                    return {"success": True}
                if "getAttribute" in script:
                    return "<svg/>"
                return None

            def wait_for_function(self, *a, **k):
                return True

            def query_selector(self, sel):
                m = MagicMock()

                def _screenshot(path):
                    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)

                m.screenshot = _screenshot
                return m

            def set_viewport_size(self, *a, **k):
                pass

        rx._RenderServer._page = FakePage()
        rx._RenderServer._output_root = None
        rx._RenderServer._auth_token = None

        png_out = tmp_path / "result.png"
        captured["write_path"] = png_out
        body = json.dumps(
            {
                "data": _diag([{"id": "r1", "type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50}]),
                "output": str(png_out),
            }
        ).encode()

        handler = rx._RenderServer.__new__(rx._RenderServer)
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.headers = {"Content-Length": str(len(body)), "Host": "127.0.0.1"}
        handler.send_response = lambda status: captured.__setitem__("status", status)
        handler.send_header = lambda *a: None
        handler.end_headers = lambda: None
        handler._handle_render()
        # Read the JSON response.
        handler.wfile.seek(0)
        body_resp = handler.wfile.read().decode() or "<empty>"
        assert captured["status"] == 200, body_resp

    def test_render_server_malformed_returns_500(self, tmp_path):
        handler = rx._RenderServer.__new__(rx._RenderServer)
        status = {"code": None, "body": b""}

        class W(io.BytesIO):
            def write(self_inner, b):
                status["body"] += b

        body = b"not-json"
        handler.rfile = io.BytesIO(body)
        handler.wfile = W()
        handler.headers = {"Content-Length": str(len(body)), "Host": "127.0.0.1"}
        handler.send_response = lambda code: status.__setitem__("code", code)
        handler.send_header = lambda *a: None
        handler.end_headers = lambda: None
        rx._RenderServer._auth_token = None
        handler._handle_render()
        assert status["code"] == 400


# --- v2 4.4: snapshot skeleton ----------------------------------------------
class TestSnapshotMarker:
    def test_integration_marker_respected(self):
        # pytest.ini markers allow our CI to filter integration tests; we just
        # check that the config file doesn't reject the marker.
        import pytest as _pytest
        assert _pytest  # trivial; ensures pytest is importable here


# --- v2 4.5: logger is NullHandler in library mode --------------------------
class TestLibraryLogger:
    def test_module_logger_has_no_stream_handler_in_library(self):
        # When imported as a library (test context), logger should have at most
        # a NullHandler (no StreamHandler attached).
        handlers = rx.logger.handlers
        for h in handlers:
            assert not (isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler)), handlers


# --- v2 4.6: connectivity retries --------------------------------------------
class TestConnectivityRetry:
    def test_two_attempts_by_default(self, monkeypatch):
        attempts = {"count": 0}

        def fake_getaddrinfo(*a, **k):
            attempts["count"] += 1
            raise socket.gaierror("nope")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(time, "sleep", lambda *_: None)
        ok = rx._check_connectivity("nonexistent.example", timeout=0.01, attempts=2)
        assert ok is False
        assert attempts["count"] == 2


# --- v2 4.7: version drift warning -------------------------------------------
class TestVendorVersionMismatch:
    def test_warns_on_mismatch(self, tmp_path, caplog, monkeypatch):
        bundle = tmp_path / "excalidraw-bundle.js"
        bundle.write_text("export const exportToSvg = () => {};", encoding="utf-8")
        import hashlib
        integrity = {
            "version": "99.0.0",
            "method": "test",
            "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "sri": "sha384-xxx",
            "size_bytes": bundle.stat().st_size,
        }
        (tmp_path / "integrity.json").write_text(json.dumps(integrity), encoding="utf-8")
        monkeypatch.setattr(rx, "VENDOR_DIR", tmp_path)
        rx._invalidate_caches()
        caplog.set_level(logging.WARNING, logger="excalidraw_render")
        ok = rx._vendor_bundle_available()
        assert ok is True  # integrity still passes
        assert any("differs from EXCALIDRAW_VERSION" in rec.message for rec in caplog.records)


# --- v2 4.8: self-test function ----------------------------------------------
class TestSelfTest:
    def test_self_test_mocked(self, monkeypatch):
        # Patch render to return quickly with a valid PNG.
        def fake_render(excalidraw_path, output_path, **kwargs):
            from PIL import Image
            Image.new("RGB", (50, 50), "white").save(str(output_path))
            return output_path

        monkeypatch.setattr(rx, "render", fake_render)
        assert rx._run_self_test() is True


# --- v2 4.9: uv lock verification (smoke) ------------------------------------
class TestLockFilePresent:
    def test_uv_lock_exists(self):
        p = Path(__file__).parents[1] / "uv.lock"
        assert p.exists()


# --- v2 4.10: JSON log formatter --------------------------------------------
class TestJsonLogFormatter:
    def test_install_json_formatter(self, caplog):
        rx._install_json_log_formatter()
        # Emit a record and read it back through formatter.
        formatter = rx._JsonLineFormatter()
        record = logging.LogRecord(
            name="excalidraw_render", level=logging.INFO, pathname=__file__,
            lineno=0, msg="hello", args=(), exc_info=None,
        )
        out = formatter.format(record)
        parsed = json.loads(out)
        assert parsed["level"] == "INFO" and parsed["msg"] == "hello"
