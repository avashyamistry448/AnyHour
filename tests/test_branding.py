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

    def test_no_old_names_in_visible_ui(self):
        for directory in ENTRY_POINTS:
            with self.subTest(entry=directory.name):
                for filename in ("index.html", "app.js"):
                    content = (directory / filename).read_text(encoding="utf-8")
                    self.assertNotIn("ClassPoint", content)
                    self.assertNotIn("ClassPilot", content)
                    self.assertNotIn("classpoint", content.lower())
                    self.assertIn("AnyHour", content)

    def test_chat_waits_at_least_2500ms_before_showing_its_answer(self):
        for directory in ENTRY_POINTS:
            with self.subTest(entry=directory.name):
                js = (directory / "app.js").read_text(encoding="utf-8")
                self.assertIn("const CHAT_MIN_RESPONSE_MS=2500;", js)
                chat = js[js.index("if(id==='chatForm')"):]
                request = chat.index("const result=await api('ask'")
                minimum_wait = chat.index("await new Promise(resolve=>setTimeout(resolve,Math.max(0,CHAT_MIN_RESPONSE_MS-(Date.now()-responseStarted))))")
                display = chat.index("state.chat.push({course_id:cid,who:'assistant',text:result.answer")
                self.assertLess(request, minimum_wait)
                self.assertLess(minimum_wait, display)
                self.assertIn("state.busy=true;const responseStarted=Date.now();render()", chat)

    def test_launch_branding_and_database_compatibility(self):
        for directory in ENTRY_POINTS:
            with self.subTest(entry=directory.name):
                server = (directory / "server.py").read_text(encoding="utf-8")
                self.assertIn("AnyHour running at", server)
                # Preserve existing database files instead of creating a fresh one.
                self.assertIn("DB=ROOT/'classpilot.db'", server)


if __name__ == "__main__":
    unittest.main()
