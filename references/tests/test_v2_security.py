"""Tests covering Section 5 (Security) of improvement plan v2."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

import render_excalidraw as rx


def _diag(elements):
    return {
        "type": "excalidraw",
        "version": 2,
        "elements": elements,
        "appState": {},
        "files": {},
    }


# --- v2 5.1: CSP no unsafe-inline --------------------------------------------
class TestCSP:
    def test_template_has_no_unsafe_inline(self):
        tmpl = (Path(__file__).parent.parent / "render_template.html").read_text()
        assert "'unsafe-inline'" not in tmpl.split("script-src", 1)[1].split(";", 1)[0], tmpl


# --- v2 5.2: security response headers ---------------------------------------
class TestSecurityHeaders:
    def test_send_json_headers(self):
        handler = rx._RenderServer.__new__(rx._RenderServer)
        headers_sent: list[tuple[str, str]] = []
        handler.send_response = lambda status: None
        handler.send_header = lambda k, v: headers_sent.append((k, v))
        handler.end_headers = lambda: None
        handler.wfile = io.BytesIO()
        handler._send_json(200, {"ok": True})
        keys = {k for k, _ in headers_sent}
        assert "X-Content-Type-Options" in keys
        assert "X-Frame-Options" in keys
        assert "Referrer-Policy" in keys


# --- v2 5.3: UNIX socket path flag -------------------------------------------
class TestSocketFlag:
    def test_socket_flag_accepted(self):
        # Indirect: the parser accepts --socket via --help.
        import subprocess

        r = subprocess.run(
            [sys.executable, "render_excalidraw.py", "--help"],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True,
            text=True,
        )
        assert "--socket" in r.stdout


# --- v2 5.4: auth token -----------------------------------------------------
class TestAuthToken:
    def test_missing_token_rejected(self):
        handler = rx._RenderServer.__new__(rx._RenderServer)
        rx._RenderServer._auth_token = "secret-token"
        rx._RenderServer._output_root = None
        status = {"code": None}
        handler.rfile = io.BytesIO(b"{}")
        handler.wfile = io.BytesIO()
        handler.headers = {"Content-Length": "2", "Host": "127.0.0.1"}
        handler.send_response = lambda code: status.__setitem__("code", code)
        handler.send_header = lambda *a: None
        handler.end_headers = lambda: None
        handler._handle_render()
        assert status["code"] == 403
        rx._RenderServer._auth_token = None

    def test_valid_token_accepted(self):
        # Auth check alone; render path will still fail with no page.
        handler = rx._RenderServer.__new__(rx._RenderServer)
        rx._RenderServer._auth_token = "tok"
        rx._RenderServer._output_root = None
        handler.headers = {
            "Authorization": "Bearer tok",
            "Host": "127.0.0.1",
            "Content-Length": "0",
        }
        ok, reason = handler._check_security()
        assert ok, reason
        rx._RenderServer._auth_token = None


# --- v2 5.5: body size cap --------------------------------------------------
class TestBodySizeCap:
    def test_oversize_rejected(self):
        handler = rx._RenderServer.__new__(rx._RenderServer)
        rx._RenderServer._auth_token = None
        rx._RenderServer._output_root = None
        status = {"code": None}
        handler.rfile = io.BytesIO(b"")
        handler.wfile = io.BytesIO()
        handler.headers = {"Content-Length": str(rx.MAX_FILE_SIZE_BYTES + 1), "Host": "127.0.0.1"}
        handler.send_response = lambda code: status.__setitem__("code", code)
        handler.send_header = lambda *a: None
        handler.end_headers = lambda: None
        handler._handle_render()
        assert status["code"] == 413


# --- v2 5.6: output-root sandbox --------------------------------------------
class TestOutputRootSandbox:
    def test_outside_root_rejected(self, tmp_path):
        handler = rx._RenderServer.__new__(rx._RenderServer)
        root = tmp_path / "sandbox"
        root.mkdir()
        rx._RenderServer._auth_token = None
        rx._RenderServer._output_root = root
        status = {"code": None}
        body = json.dumps(
            {
                "data": _diag(
                    [{"id": "r1", "type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10}]
                ),
                "output": "/etc/out.png",
            }
        ).encode()
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.headers = {"Content-Length": str(len(body)), "Host": "127.0.0.1"}
        handler.send_response = lambda code: status.__setitem__("code", code)
        handler.send_header = lambda *a: None
        handler.end_headers = lambda: None
        handler._handle_render()
        assert status["code"] == 403
        rx._RenderServer._output_root = None


# --- v2 5.7: HTML export escapes </ -----------------------------------------
class TestHtmlEscape:
    def test_script_escape(self, tmp_path):
        data = _diag(
            [
                {
                    "id": "t1",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 10,
                    "height": 10,
                    "text": "</script>alert(1)</script>",
                }
            ]
        )
        out = tmp_path / "a.html"
        rx._export_html(data, out)
        html = out.read_text(encoding="utf-8")
        # The raw terminator must not appear inside embedded JSON.
        assert "</script>alert" not in html
        assert "<\\/script>alert" in html


# --- v2 5.8: NaN/Inf seed rejected ------------------------------------------
class TestSeedFinite:
    def test_nan_rejected(self):
        errs = rx.validate_excalidraw(
            _diag(
                [
                    {
                        "id": "r1",
                        "type": "rectangle",
                        "x": 0,
                        "y": 0,
                        "width": 10,
                        "height": 10,
                        "seed": float("nan"),
                    }
                ]
            )
        )
        assert any("NaN or infinity" in e for e in errs)

    def test_inf_rejected(self):
        errs = rx.validate_excalidraw(
            _diag(
                [
                    {
                        "id": "r1",
                        "type": "rectangle",
                        "x": 0,
                        "y": 0,
                        "width": 10,
                        "height": 10,
                        "versionNonce": float("inf"),
                    }
                ]
            )
        )
        assert any("NaN or infinity" in e for e in errs)


# --- v2 5.9: protocol-relative URLs ------------------------------------------
class TestProtocolRelativeURL:
    def test_slash_slash_rejected(self):
        errs = rx.validate_excalidraw(
            _diag(
                [
                    {
                        "id": "r1",
                        "type": "rectangle",
                        "x": 0,
                        "y": 0,
                        "width": 10,
                        "height": 10,
                        "link": "//evil.com/xss",
                    }
                ]
            )
        )
        assert any("protocol-relative" in e for e in errs)

    def test_backslash_rejected(self):
        errs = rx.validate_excalidraw(
            _diag(
                [
                    {
                        "id": "r1",
                        "type": "rectangle",
                        "x": 0,
                        "y": 0,
                        "width": 10,
                        "height": 10,
                        "link": "\\\\server\\share",
                    }
                ]
            )
        )
        assert any("protocol-relative" in e for e in errs)


# --- v2 5.10: SECURITY.md exists ---------------------------------------------
class TestSecurityDoc:
    def test_security_md_present(self):
        p = Path(__file__).parents[2] / "SECURITY.md"
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "Reporting a Vulnerability" in text
        assert "SECURITY.md" not in text or "disclosure" in text.lower()
