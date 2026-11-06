import json
import sqlite3
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import ui
from ui_data import SavedAnalyses, build_data, load_data


def snapshot(text="보고서를 제출하세요."):
    return {"fetched_at": "2026-11-05T12:00:00Z", "complete": True,
            "courses": [{"id": "c", "name": "수학"}],
            "assignments": [{"id": "a", "course_id": "c", "source": "coursework", "course_name": "수학", "title": "보고서",
                             "text": text, "due_at": "2026-11-08T23:59:00+09:00", "original_url": "https://classroom.google.com/example",
                             "raw": {"creationTime": "2026-11-01T00:00:00Z"}}], "announcements": [], "materials": []}


class UiDataTests(unittest.TestCase):
    def test_pending_api_data_is_kept_without_inventing_analysis(self):
        cache = Mock()
        cache.get.return_value = None
        result = build_data(snapshot(), cache, "https://example.invalid", date(2026, 11, 6))
        self.assertEqual(result["stats"]["analyzed"], 0)
        self.assertEqual(result["tasks"][0]["status"], "pending")
        self.assertFalse(result["tasks"][0]["analyzed"])
        self.assertEqual(result["tasks"][0]["due"], "2026-11-08T23:59:00+09:00")
        self.assertTrue(result["tasks"][0]["apiDue"])
        self.assertTrue(result["tasks"][0]["deadlineConfirmed"])

    def test_pdf_source_and_private_tokens_are_not_mixed_into_ui_data(self):
        source = snapshot()
        source["assignments"][0]["raw"]["creatorUserId"] = "private-id"
        source["assignments"][0]["raw"]["individualStudentsOptions"] = {"studentIds": ["private-student"]}
        source["assignments"][0]["attachments"] = [{"file_id": "f", "title": "guide.pdf", "status": "text_extracted", "pages": [{"page": 1, "text": "제출 기한"}]}]
        cache = Mock()
        cache.get.return_value = None
        result = build_data(source, cache, "https://example.invalid", date(2026, 11, 6))
        self.assertNotIn("private-student", json.dumps(result))
        self.assertNotIn("private-id", json.dumps(result))
        self.assertEqual(result["posts"][0]["attachments"][0]["pages"][0]["page"], 1)

    def test_missing_database_never_creates_one(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite3"
            cache = SavedAnalyses(path)
            self.assertIsNone(cache.get("any"))
            cache.close()
            self.assertFalse(path.exists())

    def test_existing_database_is_read_only(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE analyses (key TEXT, status TEXT, result TEXT)")
            connection.commit()
            connection.close()
            cache = SavedAnalyses(path)
            with self.assertRaises(sqlite3.OperationalError):
                cache.connection.execute("INSERT INTO analyses VALUES ('x','success','{}')")
            cache.close()

    def test_in_progress_analysis_does_not_break_dashboard_reads(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"analysis.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE analyses (key TEXT,status TEXT,result TEXT)")
                connection.execute("INSERT INTO analyses VALUES ('running','processing',NULL)")
            connection.close()
            cache=SavedAnalyses(path)
            try:
                self.assertEqual(cache.get("running"),{"status":"processing","result":None})
            finally:
                cache.close()

    def test_html_export_escapes_data_script_boundary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".local" / "classroom").mkdir(parents=True)
            (root / "web").mkdir()
            (root / ".local" / "classroom" / "snapshot.json").write_text("{}", encoding="utf-8")
            (root / "web" / "index.html").write_text('<script type="application/json">{{DATA}}</script><style>{{STYLE}}</style><script>{{SCRIPT}}</script>', encoding="utf-8")
            (root / "web" / "app.css").write_text("body{}", encoding="utf-8")
            (root / "web" / "app.js").write_text("void 0;", encoding="utf-8")
            fake = {"courses": [], "posts": [], "stats": {"analyzed": 0}, "text": '</script><script>alert("x")</script>{{SCRIPT}}'}
            with patch.object(ui, "ROOT", root), patch.object(ui, "OUTPUT", root / "output.html"), patch.object(ui, "load_data", return_value=fake), patch.dict("os.environ", {"BAZE_BASE_URL": "https://example.invalid"}):
                ui.export(date(2026, 11, 6))
            rendered = (root / "output.html").read_text(encoding="utf-8")
            self.assertIn(r"\u003c/script\u003e", rendered)
            self.assertNotIn('<script>alert("x")', rendered)
            self.assertIn("{{SCRIPT}}", rendered)


if __name__ == "__main__":
    unittest.main()
