from datetime import date
import unittest
from unittest.mock import Mock

from opportunities import candidate, collect


class OpportunityTests(unittest.TestCase):
    def post(self, text="참여 희망자는 신청하세요.", source="announcement"):
        return {"id": "p", "course_id": "c", "source": source, "title": "AI 경진대회 안내", "text": text,
                "due_at": "2026-11-30T23:59:00+09:00", "raw": {"creationTime": "2026-11-01T00:00:00Z"}}

    def collect(self, items=None, post=None):
        cache = Mock()
        cache.get.return_value = None if items is None else {"status": "success", "result": {"items": items}}
        return collect([{"key": "k", "post": post or self.post()}], cache, date(2026, 11, 6))

    def test_unanalyzed_candidate_never_borrows_assignment_date(self):
        row = self.collect()[0]
        self.assertFalse(row["analyzed"])
        self.assertFalse(row["optionalConfirmed"])
        self.assertEqual(row["dates"], [])
        self.assertIsNone(row["nextDeadline"])

    def test_application_school_signup_and_event_dates_stay_separate(self):
        items = [{"task_status": "optional", "deadline_kind": kind, "deadline": value,
                  "deadline_evidence": "신청 근거", "deadline_evidence_source": "pdf:f:2"}
                 for kind, value in [("registration", "2026-11-20"), ("local_signup", "2026-11-10"), ("event", "2026-12-01")]]
        row = self.collect(items)[0]
        self.assertEqual(row["nextDeadline"], "2026-11-10")
        self.assertEqual([d["kind"] for d in row["dates"]], ["registration", "local_signup", "event"])
        self.assertEqual(row["dates"][0]["source"], "pdf:f:2")

    def test_event_date_is_not_application_deadline(self):
        row = self.collect([{"task_status": "optional", "deadline_kind": "event", "proposed_deadline": "2026-11-20"}])[0]
        self.assertIsNone(row["nextDeadline"])
        self.assertFalse(row["closed"])

    def test_estimated_past_date_is_not_confirmed_closed(self):
        row = self.collect([{"task_status": "optional", "deadline_kind": "registration", "proposed_deadline": "2026-10-30"}])[0]
        self.assertTrue(row["past"])
        self.assertFalse(row["closed"])
        self.assertFalse(row["dates"][0]["confirmed"])

    def test_exact_application_date_is_independent_of_obligation(self):
        row = self.collect([{"task_status": "unknown", "proposed_task_status": "optional", "deadline_kind": "registration",
                             "proposed_deadline": "2026-10-25", "deadline": None,
                             "deadline_evidence": "신청기간: 2026. 10. 5.(월) - 2026. 10. 25.(일)"}])[0]
        self.assertFalse(row["optionalConfirmed"])
        self.assertTrue(row["dates"][0]["confirmed"])
        self.assertTrue(row["closed"])

    def test_one_past_school_date_does_not_close_future_external_application(self):
        row = self.collect([{"task_status": "optional", "deadline_kind": "local_signup", "deadline": "2026-11-01"},
                            {"task_status": "optional", "deadline_kind": "registration", "deadline": "2026-11-20"}])[0]
        self.assertFalse(row["closed"])
        self.assertFalse(row["past"])

    def test_compulsory_contest_submission_not_advertised_as_opt_in(self):
        self.assertEqual(self.collect([{"task_status": "required", "deadline_kind": "submission"}]), [])

    def test_choosing_one_compulsory_subject_does_not_make_opportunity(self):
        post = self.post("보고서 주제 중 하나를 선택하세요.")
        post["title"] = "보고서"
        self.assertFalse(candidate(post))


if __name__ == "__main__":
    unittest.main()
