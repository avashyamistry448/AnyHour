"""Ensure all bundled entry points use the same visible application name."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = (ROOT, ROOT / "classpilot-v5", ROOT / "AnyHour-student-v6")


class BrandingTests(unittest.TestCase):
    def test_browser_title_and_sidebar_brand(self):
        for directory in ENTRY_POINTS:
            with self.subTest(entry=directory.name):
                page = (directory / "index.html").read_text(encoding="utf-8")
                self.assertIn("<title>AnyHour | Course Workspace</title>", page)
                self.assertIn('<span>AnyHour<span style="color:#8495ff">.</span></span>', page)

    def test_launch_branding_and_database_compatibility(self):
        for directory in ENTRY_POINTS:
            with self.subTest(entry=directory.name):
                server = (directory / "server.py").read_text(encoding="utf-8")
                self.assertIn("AnyHour running at", server)
                # Preserve existing database files instead of creating a fresh one.
                self.assertIn("DB=ROOT/'classpilot.db'", server)


if __name__ == "__main__":
    unittest.main()
