from datetime import date
import unittest
from unittest.mock import Mock

from task_report import card, gather
from task_priority import prioritize_posts


class TaskReportTests(unittest.TestCase):
    def post(self, due=None, title="보고서", created="2026-11-01T00:00:00Z"):
        return {"id": "p", "course_id": "c", "source": "coursework", "title": title,
                "text": "본문", "due_at": due, "raw": {"creationTime": created}}

    def test_api_deadline_keeps_exact_time_when_ai_proposed_day_matches(self):
        post = self.post("2026-11-08T23:59:00+09:00")
        item = {"title": "발표자료 제출", "action": "PDF를 제출하세요.", "proposed_task_status": "required",
                "task_status": "required", "proposed_deadline": "2026-11-08", "deadline": None,
                "deadline_kind": "submission", "review_flags": ["deadline_unverified"]}
        cache = Mock()
        cache.get.return_value = {"status": "success", "result": {"items": [item]}}
        groups, count = gather([{"key": "current", "post": post}], cache, date(2026, 11, 5))
        row = groups["tasks"][0]
        self.assertEqual(row["due"], "2026-11-08T23:59:00+09:00")
        self.assertTrue(row["api_due"])
        self.assertNotIn("추정", card(row))

    def test_past_and_undated_unanalyzed_entries_do_not_fill_current_tasks(self):
        cache = Mock()
        cache.get.return_value = None
        groups, count = gather([{"key": "a", "post": self.post("2026-04-01T10:00:00+09:00")},
                                {"key": "b", "post": self.post()}], cache, date(2026, 11, 5))
        self.assertEqual(count, 0)
        self.assertEqual(len(groups["past"]), 1)
        self.assertEqual(len(groups["pending"]), 1)
        self.assertEqual(groups["tasks"], [])
        self.assertEqual(groups["uncertain"], [])

    def test_reference_result_is_separated_from_actionable_tasks(self):
        cache = Mock()
        cache.get.return_value = {"status": "success", "result": {"items": [{"title": "시험 범위", "task_status": "reference"}]}}
        groups, count = gather([{"key": "current-upgraded-only", "post": self.post()}], cache, date(2026, 11, 5))
        self.assertEqual(len(groups["reference"]), 1)
        self.assertEqual(groups["tasks"], [])
        cache.get.assert_called_once_with("current-upgraded-only")

    def test_report_escapes_html_and_rejects_javascript_links(self):
        row = {"post": {**self.post(), "original_url": "javascript:alert(1)"}, "item": {"title": "<script>alert(1)</script>"},
               "due": None, "status": "pending", "analyzed": False}
        rendered = card(row)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("javascript:", rendered)

    def test_scheduler_prefers_upcoming_work_over_latest_reference(self):
        due = self.post("2026-11-08T23:59:00+09:00", created="2026-10-01T00:00:00Z")
        reference = {**self.post(title="시험 안내", created="2026-11-05T00:00:00Z"), "source": "announcement"}
        self.assertIs(prioritize_posts([reference, due], date(2026, 11, 5))[0], due)


if __name__ == "__main__":
    unittest.main()
