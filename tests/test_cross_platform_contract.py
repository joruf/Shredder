"""Contract tests for Secure Trash Shredder (Linux-only app)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dependencies_setup as deps  # noqa: E402


class TestDependenciesContract(unittest.TestCase):
    def test_tkinter_probe_returns_bool(self) -> None:
        self.assertIsInstance(deps.is_tkinter_available(), bool)

    def test_pkexec_probe_returns_bool(self) -> None:
        self.assertIsInstance(deps.is_pkexec_available(), bool)


class TestProjectLayout(unittest.TestCase):
    def test_main_script_exists(self) -> None:
        self.assertTrue((ROOT / "shredder.py").is_file())

    def test_desktop_helpers_exist(self) -> None:
        self.assertTrue((ROOT / "desktop_setup.py").is_file())
        self.assertTrue((ROOT / "nemo_setup.py").is_file())

    def test_linux_only_documented_in_readme(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Linux", text)


if __name__ == "__main__":
    unittest.main()
