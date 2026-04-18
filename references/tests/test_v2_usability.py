"""Tests covering Section 6 (Usability) of improvement plan v2."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import render_excalidraw as rx


# --- v2 6.1: SKILL.md deep-dive companion ------------------------------------
class TestDeepDive:
    def test_deep_dive_present(self):
        p = Path(__file__).parent.parent / "skill-deep-dive.md"
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "Deep Dive" in text


# --- v2 6.2: setup.sh --------------------------------------------------------
class TestSetupScript:
    def test_setup_script_exists(self):
        p = Path(__file__).parent.parent / "setup.sh"
        assert p.exists()
        assert p.stat().st_mode & 0o111, "setup.sh should be executable"

    def test_setup_script_shebang(self):
        p = Path(__file__).parent.parent / "setup.sh"
        assert p.read_text(encoding="utf-8").startswith("#!")


# --- v2 6.3: lint summary output --------------------------------------------
class TestLintSummary:
    def test_lint_prints_summary(self, tmp_path):
        p = tmp_path / "d.excalidraw"
        p.write_text(
            json.dumps(
                {
                    "type": "excalidraw",
                    "version": 2,
                    "elements": [],
                    "appState": {},
                    "files": {},
                }
            ),
            encoding="utf-8",
        )
        r = subprocess.run(
            [sys.executable, "lint_excalidraw.py", str(p)],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True,
            text=True,
        )
        assert "Lint:" in r.stdout


# --- v2 6.4: SKILL.md mentions server mode ----------------------------------
class TestSkillMdServerMode:
    def test_server_section_present(self):
        p = Path(__file__).parents[2] / "SKILL.md"
        text = p.read_text(encoding="utf-8")
        assert "Render Server Mode" in text
        assert "--server" in text


# --- v2 6.5: JSONPath in validator errors -----------------------------------
class TestJsonPathErrors:
    def test_errors_include_index(self):
        data = {
            "type": "excalidraw",
            "version": 2,
            "elements": [{"id": "a"}, {"id": "b"}],  # missing "type"
            "appState": {},
            "files": {},
        }
        errors = rx.validate_excalidraw(data)
        assert any("$.elements[" in e for e in errors)


# --- v2 6.6: OS-specific guidance -------------------------------------------
class TestOsGuidance:
    def test_verify_setup_output_has_platform(self, capsys, monkeypatch):
        # Patch Chromium launch to fail; verify OS-specific hint in output.
        import render_excalidraw as r
        import playwright.sync_api as sync_api  # noqa: F401

        class _FailingCM:
            def __enter__(self_inner):
                raise Exception("chromium missing")

            def __exit__(self_inner, *a):
                return False

        monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _FailingCM())
        # _verify_setup exits on failure; wrap.
        with pytest.raises(SystemExit):
            r._verify_setup()
        captured = capsys.readouterr().out
        assert "Chromium" in captured


# --- v2 6.7: skill frontmatter manifest -------------------------------------
class TestSkillManifest:
    def test_frontmatter_has_version(self):
        p = Path(__file__).parents[2] / "SKILL.md"
        text = p.read_text(encoding="utf-8")
        fm = text.split("---", 2)[1]
        assert "version:" in fm
        assert "tags:" in fm
        assert "requires:" in fm


# --- v2 6.8: --help-examples ------------------------------------------------
class TestHelpExamples:
    def test_help_examples_prints_recipes(self, capsys):
        rx._print_help_examples()
        out = capsys.readouterr().out
        assert "--all" in out
        assert "curl" in out


# --- v2 6.9: cross-platform open --------------------------------------------
class TestCrossPlatformOpen:
    def test_linux_falls_back(self, monkeypatch, tmp_path):
        # Simulate Linux with no xdg-open.
        monkeypatch.setattr("platform.system", lambda: "Linux")
        monkeypatch.setattr("shutil.which", lambda name: None)
        target = tmp_path / "file.png"
        target.write_bytes(b"x")
        # Should not raise.
        rx._open_file(target)

    def test_wsl_uses_explorer(self, monkeypatch, tmp_path):
        monkeypatch.setattr("platform.system", lambda: "Linux")
        # Fake /proc/version with "microsoft" in it.
        fake_text = "Linux version 5.10 (Microsoft Corp)"
        monkeypatch.setattr(
            Path,
            "read_text",
            lambda self, **kw: (
                fake_text if str(self) == "/proc/version" else Path.read_text(self, **kw)
            ),
        )
        calls = []

        class _FakePopen:
            def __init__(self, cmd):
                calls.append(cmd[0])

        monkeypatch.setattr("subprocess.Popen", _FakePopen)
        target = tmp_path / "file.png"
        target.write_bytes(b"x")
        rx._open_file(target)
        assert "explorer.exe" in calls


# --- v2 6.10: --quiet flag --------------------------------------------------
class TestQuiet:
    def test_quiet_flag_suppresses_info(self):
        r = subprocess.run(
            [sys.executable, "render_excalidraw.py", "--help"],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True,
            text=True,
        )
        assert "--quiet" in r.stdout
