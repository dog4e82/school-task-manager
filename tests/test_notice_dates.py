from datetime import date, datetime
import unittest
from unittest.mock import Mock

from notice_dates import extract_dates, post_dates, reconcile_dates, deadline_past
from notice_ai import grounded_date
from opportunities import collect
from deadline_schedule import combine


ROBOT = "접수기간: 2026. 10. 8.(목) 18:00~11. 2.(월) 18:00\n참가를 원하는 학생은 이번주 금요일까지 정보연구실 황지영T에게 말해주세요."
CREATED = "2026-10-20T01:00:00Z"


class NoticeDateTests(unittest.TestCase):
    def test_inherits_range_year_and_preserves_end_time(self):
        dates = extract_dates(ROBOT, CREATED)
        registration = next(d for d in dates if d["kind"] == "registration")
        school = next(d for d in dates if d["kind"] == "local_signup")
        self.assertEqual(registration["date"], "2026-11-02T18:00:00+09:00")
        self.assertEqual(registration["start"], "2026-10-08T18:00:00+09:00")
        self.assertTrue(registration["confirmed"])
        self.assertEqual(school["date"], "2026-10-23")
        self.assertFalse(school["confirmed"])
        for entry in dates:
            self.assertIn(entry["evidence"], ROBOT)

    def test_range_year_is_grounded_for_existing_ai_cache(self):
        self.assertTrue(grounded_date("2026-11-02", ROBOT.splitlines()[0], "registration"))
        self.assertFalse(grounded_date("2026-10-08", ROBOT.splitlines()[0], "registration"))

    def test_no_fake_time_or_confident_year_on_yearless_date(self):
        result = extract_dates("신청 기한: 11월 13일까지", CREATED)[0]
        self.assertEqual(result["date"], "2026-11-13")
        self.assertFalse(result["confirmed"])
        self.assertEqual(extract_dates("신청 기한: 11월 13일까지"), [])

    def test_event_publication_and_unknown_registration_never_become_deadline(self):
        for text in ("행사일: 2026. 11. 20.", "공개일: 2026. 11. 20.",
                     "신청 기간: 추후 공지. 행사일: 2026. 11. 20."):
            self.assertEqual(extract_dates(text, CREATED), [])

    def test_unreadable_range_end_is_not_replaced_with_start(self):
        self.assertEqual(extract_dates("접수기간: 2026.11.1.~미정", CREATED), [])
        self.assertFalse(grounded_date("2026-11-01", "접수기간: 2026.11.1.~미정", "registration"))

    def test_relative_day_uses_published_seoul_date_not_run_date(self):
        entry = extract_dates("참가 희망자는 내일까지 선생님께 말해주세요.", "2026-10-22T16:00:00Z")[0]
        self.assertEqual(entry["date"], "2026-10-24")
        self.assertFalse(entry["confirmed"])

    def test_weekday_disagreement_is_marked_uncertain(self):
        entry = extract_dates("신청기간: 2026.11.2.(금) 18:00", CREATED)[0]
        self.assertFalse(entry["confirmed"])
        self.assertIn("weekday_mismatch", entry["flags"])

    def test_date_without_time_does_not_borrow_start_time(self):
        entry = extract_dates("접수기간: 2026.10.8. 18:00~11.2.", CREATED)[0]
        self.assertEqual(entry["date"], "2026-11-02")

    def test_pdf_page_provenance_is_kept(self):
        post = {"text": "첨부 참고", "raw": {"creationTime": CREATED}, "attachments": [
            {"file_id": "pdf1", "pages": [{"page": 2, "text": ROBOT}]}]}
        self.assertTrue(all(d["source"] == "pdf:pdf1:2" for d in post_dates(post)))

    def test_source_range_repairs_ai_start_date_and_lost_time_without_new_call(self):
        rule = extract_dates(ROBOT, CREATED)
        entry = {"kind": "registration", "date": "2026-10-08", "source": "post", "confirmed": False,
                 "expression": "2026. 10. 8.(목) 18:00~11. 2.(월) 18:00"}
        result = reconcile_dates([entry], rule)
        registration = [d for d in result if d["kind"] == "registration"]
        self.assertEqual(len(registration), 1)
        self.assertEqual(registration[0]["date"], "2026-11-02T18:00:00+09:00")

    def test_conflicting_pdf_and_post_times_are_not_silently_resolved(self):
        entries = [{"kind": "registration", "date": f"2026-11-02T{hour}:00:00+09:00", "confirmed": True, "source": source}
                   for hour, source in [("17", "post"), ("18", "pdf:p:1")]]
        result = reconcile_dates([], entries)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(not d["confirmed"] for d in result))

    def test_explicit_teacher_date_separate_from_external_application(self):
        dates = extract_dates("참가 희망자는 2026.10.23.(금)까지 선생님께 말해주세요. 접수 마감: 2026.11.2. 18:00", CREATED)
        self.assertEqual({d["kind"] for d in dates}, {"local_signup", "registration"})

    def test_unanalyzed_notice_has_source_dates_and_distinct_dashboard_entries(self):
        post = {"id": "r", "course_id": "c", "course_name": "안내", "source": "material", "title": "로보틱스 작품공모전",
                "text": ROBOT, "raw": {"creationTime": CREATED}}
        cache = Mock()
        cache.get.return_value = None
        opportunities = collect([{"post": post, "key": "k"}], cache, date(2026, 10, 22))
        self.assertFalse(opportunities[0]["analyzed"])
        self.assertFalse(opportunities[0]["optionalConfirmed"])
        schedule = combine([], opportunities)
        self.assertEqual(len(schedule), 2)
        self.assertEqual({t["deadlineKind"] for t in schedule}, {"registration", "local_signup"})
        self.assertEqual(len({t["id"] for t in schedule}), 2)
        self.assertTrue(all(t["type"] == "opportunity" for t in schedule))

    def test_exact_deadline_time_expires_but_date_only_does_not_invent_time(self):
        at = datetime.fromisoformat("2026-11-02T18:01:00+09:00")
        self.assertTrue(deadline_past("2026-11-02T18:00:00+09:00", at.date(), at))
        self.assertFalse(deadline_past("2026-11-02T19:00:00+09:00", at.date(), at))
        self.assertFalse(deadline_past("2026-11-02", at.date(), at))


if __name__ == "__main__":
    unittest.main()
