#!/usr/bin/env bash
# (v2 6.2) One-shot setup for the Excalidraw Diagram Skill.
#
# This script:
#   1) Syncs Python dependencies with uv.
#   2) Installs the Chromium runtime Playwright needs.
#   3) Runs the renderer's --check self-test to confirm it works.
#
# Re-run any time after pulling new dependency changes.

set -euo pipefail

cd "$(dirname "$0")"

echo "==> Installing Python dependencies with uv..."
uv sync --dev

echo "==> Installing Chromium for Playwright..."
uv run playwright install chromium

echo "==> Running self-check..."
uv run python render_excalidraw.py --check

echo "==> Setup complete."
