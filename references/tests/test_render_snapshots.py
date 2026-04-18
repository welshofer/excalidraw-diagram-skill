"""Golden-image snapshot tests for example diagrams (v2 4.4).

These tests live behind the ``integration`` marker and are only executed in the
CI job that already has Chromium installed. They render each example via the
actual render pipeline and compare against ``tests/snapshots/*.png`` via
Pillow's pixel diff.

To regenerate snapshots after intentional output changes:

    cd references
    uv run python -m pytest tests/test_render_snapshots.py \
        --update-snapshots -m integration
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


ROOT = Path(__file__).parents[2]
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Regenerate stored snapshots instead of comparing.",
    )


@pytest.fixture(scope="session")
def update_snapshots(request):
    return request.config.getoption("--update-snapshots", default=False)


def _diff_pixels(a_path: Path, b_path: Path) -> int:
    from PIL import Image, ImageChops

    with Image.open(a_path) as a, Image.open(b_path) as b:
        if a.size != b.size:
            # Resize b to a's size so we can still compare.
            b = b.resize(a.size)
        diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
        return max(e for e in diff.getextrema() for e in [e[1]])


EXAMPLE_NAMES = (
    "simple-flow",
    "decision-flow",
    "all-patterns",
)


@pytest.mark.integration
@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_snapshot(name, tmp_path, update_snapshots):
    import render_excalidraw as rx

    input_path = ROOT / "examples" / f"{name}.excalidraw"
    if not input_path.exists():
        pytest.skip(f"{input_path} missing")

    output_path = tmp_path / f"{name}.png"
    rx.render(input_path, output_path, scale=2, force=True)

    snapshot_path = SNAPSHOT_DIR / f"{name}.snapshot.png"
    if update_snapshots or not snapshot_path.exists():
        import shutil

        shutil.copy2(str(output_path), str(snapshot_path))
        pytest.skip(f"Snapshot created at {snapshot_path}")

    max_diff = _diff_pixels(snapshot_path, output_path)
    assert max_diff <= 5, f"{name} differs from snapshot by max pixel delta {max_diff}"
