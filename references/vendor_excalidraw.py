"""Download and vendor the Excalidraw library for offline use (1.10).

Usage:
    cd references
    python vendor_excalidraw.py

    # Or with uv:
    uv run python vendor_excalidraw.py

Prerequisites: npm must be installed (used to fetch and bundle via esbuild).

This script:
1. Creates a temp workspace, installs @excalidraw/excalidraw + esbuild via npm
2. Bundles everything into a single self-contained IIFE JS file
3. Saves it to vendor/excalidraw-bundle.js with integrity hashes
4. The render script auto-detects vendor/ and uses it when available
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXCALIDRAW_VERSION = "0.18.0"
VENDOR_DIR = Path(__file__).parent / "vendor"
BUNDLE_PATH = VENDOR_DIR / "excalidraw-bundle.js"
INTEGRITY_PATH = VENDOR_DIR / "integrity.json"


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command, raise on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result.stdout


def build_bundle() -> Path:
    """Build a self-contained Excalidraw bundle using npm + esbuild."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="excalidraw-vendor-") as tmpdir:
        tmppath = Path(tmpdir)
        print(f"Building Excalidraw v{EXCALIDRAW_VERSION} bundle...")

        # Create package.json
        pkg = {
            "name": "excalidraw-vendor-build",
            "private": True,
            "dependencies": {
                "@excalidraw/excalidraw": EXCALIDRAW_VERSION,
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
            },
            "devDependencies": {
                "esbuild": "^0.24.0",
            },
        }
        (tmppath / "package.json").write_text(json.dumps(pkg, indent=2))

        # Entry point that re-exports what we need
        (tmppath / "entry.js").write_text(
            'export { exportToSvg, exportToBlob } from "@excalidraw/excalidraw";\n'
        )

        # Install dependencies
        print("  Installing npm dependencies...")
        _run(["npm", "install", "--no-audit", "--no-fund"], cwd=tmppath)

        # Bundle with esbuild into a single file
        print("  Bundling with esbuild...")
        _run([
            str(tmppath / "node_modules" / ".bin" / "esbuild"),
            str(tmppath / "entry.js"),
            "--bundle",
            "--format=esm",
            "--platform=browser",
            "--target=es2020",
            f"--outfile={str(BUNDLE_PATH)}",
            "--minify",
            "--define:process.env.NODE_ENV=\"production\"",
            # Externalize nothing -- we want a fully self-contained bundle
        ], cwd=tmppath)

    content = BUNDLE_PATH.read_bytes()
    size_mb = len(content) / (1024 * 1024)

    # Compute integrity hashes (5.10)
    sha256_hash = hashlib.sha256(content).hexdigest()
    sha384_b64 = base64.b64encode(hashlib.sha384(content).digest()).decode("ascii")
    sri_hash = f"sha384-{sha384_b64}"

    integrity = {
        "version": EXCALIDRAW_VERSION,
        "method": "npm+esbuild",
        "sha256": sha256_hash,
        "sri": sri_hash,
        "size_bytes": len(content),
    }
    INTEGRITY_PATH.write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")

    print(f"  Saved to: {BUNDLE_PATH} ({size_mb:.1f} MB)")
    print(f"  SHA-256:  {sha256_hash}")
    print(f"  SRI:      {sri_hash}")
    print(f"  Integrity file: {INTEGRITY_PATH}")
    return BUNDLE_PATH


def verify_bundle() -> bool:
    """Verify the vendored bundle against stored integrity hashes."""
    if not BUNDLE_PATH.exists() or not INTEGRITY_PATH.exists():
        return False
    try:
        integrity = json.loads(INTEGRITY_PATH.read_text(encoding="utf-8"))
        content = BUNDLE_PATH.read_bytes()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        return actual_sha256 == integrity.get("sha256")
    except (json.JSONDecodeError, OSError):
        return False


def main() -> None:
    if "--verify" in sys.argv:
        if verify_bundle():
            print("Vendor bundle integrity: OK")
        else:
            print("Vendor bundle integrity: FAILED (re-run vendor_excalidraw.py to re-download)")
            sys.exit(1)
        return

    # Check npm is available
    if not shutil.which("npm"):
        print("Error: npm is required to build the vendor bundle.")
        print("Install Node.js from https://nodejs.org/ or via your package manager.")
        sys.exit(1)

    build_bundle()

    if verify_bundle():
        print("\nIntegrity verification: PASSED")
    else:
        print("\nIntegrity verification: FAILED")
        sys.exit(1)

    print(f"\nVendor setup complete. The render script will auto-detect {VENDOR_DIR}/")
    print("To verify later: python vendor_excalidraw.py --verify")


if __name__ == "__main__":
    main()
