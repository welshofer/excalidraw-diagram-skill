"""Tests for vendor bundle detection and integrity verification (1.10, 5.10)."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent.parent))

from render_excalidraw import (
    _vendor_bundle_available,
    _get_vendor_sri,
    _resolve_template_html,
)
from vendor_excalidraw import verify_bundle


class TestVendorDetection:
    """Test vendor bundle detection (1.10)."""

    def test_vendor_available_when_bundle_and_integrity_exist(self):
        """When vendor dir has valid bundle + integrity, detection succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            content = b"fake bundle content for testing"
            (vendor_dir / "excalidraw-bundle.js").write_bytes(content)
            sha256 = hashlib.sha256(content).hexdigest()
            integrity = {"sha256": sha256, "version": "0.18.0"}
            (vendor_dir / "integrity.json").write_text(json.dumps(integrity))

            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                assert _vendor_bundle_available() is True

    def test_vendor_unavailable_when_no_bundle(self):
        """When vendor dir is empty, detection fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                assert _vendor_bundle_available() is False

    def test_vendor_unavailable_when_integrity_mismatch(self):
        """When integrity hash doesn't match, detection fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            (vendor_dir / "excalidraw-bundle.js").write_bytes(b"real content")
            integrity = {"sha256": "wrong_hash_value", "version": "0.18.0"}
            (vendor_dir / "integrity.json").write_text(json.dumps(integrity))

            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                assert _vendor_bundle_available() is False


class TestVendorSRI:
    """Test SRI hash retrieval (5.10)."""

    def test_get_sri_from_integrity_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            integrity = {"sri": "sha384-testvalue123", "version": "0.18.0"}
            (vendor_dir / "integrity.json").write_text(json.dumps(integrity))

            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                sri = _get_vendor_sri()
                assert sri == "sha384-testvalue123"

    def test_get_sri_returns_none_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                assert _get_vendor_sri() is None


class TestResolveTemplate:
    """Test template resolution with/without vendor (1.10)."""

    def test_uses_cdn_template_without_vendor(self):
        """Without vendor dir, the CDN-based template is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            # No bundle in vendor dir
            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                html = _resolve_template_html()
                assert "esm.sh" in html
                assert "exportToSvg" in html

    def test_uses_vendor_template_when_available(self):
        """With valid vendor bundle, the inline template is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vendor_dir = Path(tmpdir) / "vendor"
            vendor_dir.mkdir()
            bundle_content = b'export function exportToSvg() { return "test"; }'
            (vendor_dir / "excalidraw-bundle.js").write_bytes(bundle_content)
            sha256 = hashlib.sha256(bundle_content).hexdigest()
            integrity = {"sha256": sha256, "version": "0.18.0"}
            (vendor_dir / "integrity.json").write_text(json.dumps(integrity))

            with patch("render_excalidraw.VENDOR_DIR", vendor_dir):
                html = _resolve_template_html()
                assert "Vendor bundle loaded locally" in html
                assert "esm.sh" not in html
                assert "blob:" in html.lower() or "Blob" in html


class TestVendorVerify:
    """Test vendor_excalidraw.py verify_bundle function."""

    def test_verify_fails_without_files(self):
        with patch("vendor_excalidraw.BUNDLE_PATH", Path("/nonexistent/bundle.js")):
            with patch("vendor_excalidraw.INTEGRITY_PATH", Path("/nonexistent/integrity.json")):
                assert verify_bundle() is False
