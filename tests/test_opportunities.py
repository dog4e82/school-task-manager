from datetime import date
import unittest
from unittest.mock import Mock

from opportunities import candidate, collect
from deadline_schedule import combine


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

    def test_two_activities_in_one_notice_keep_separate_cards_and_same_day_deadlines(self):
        p = self.post('희망자는 로봇 공모전과 탐구 캠프에 각각 신청하세요.')
        items = [{'title': title, 'task_status': 'optional', 'deadline_kind': 'registration',
                  'deadline': '2026-11-20', 'task_evidence': title, 'task_evidence_source': 'post'}
                 for title in ('로봇 공모전', '탐구 캠프')]
        rows = self.collect(items, p)
        self.assertEqual({r['title'] for r in rows}, {'로봇 공모전', '탐구 캠프'})
        self.assertEqual(len({r['id'] for r in rows}), 2)
        self.assertEqual(len({r['postId'] for r in rows}), 1)
        schedule = combine([], rows)
        self.assertEqual(len(schedule), 2)
        self.assertEqual(len({r['id'] for r in schedule}), 2)
        self.assertEqual({r['opportunityId'] for r in schedule}, {r['id'] for r in rows})

    def test_numbered_activities_do_not_borrow_each_others_dates(self):
        p = self.post('1. 로봇 공모전 신청\n희망자는 신청하세요.\n접수기간: 2026.11.1.~2026.11.12.\n'
                      '2. 탐구 캠프 신청\n희망자는 신청하세요.\n접수기간: 2026.11.1.~2026.11.25.')
        rows = self.collect(post=p)
        self.assertEqual({r['title']: r['nextDeadline'] for r in rows},
                         {'로봇 공모전 신청': '2026-11-12', '탐구 캠프 신청': '2026-11-25'})
        self.assertTrue(all(len(r['dates']) == 1 for r in rows))

    def test_unrelated_activity_does_not_hide_optional_task_with_unknown_deadline(self):
        rows = self.collect([{'title': '대회 신청', 'task_status': 'optional',
                              'deadline_kind': 'registration', 'deadline': '2026-11-20'}])
        task = {'id': 'extra', 'postId': rows[0]['postId'], 'title': '선택 심화 문제',
                'status': 'optional', 'deadlineKind': 'submission', 'due': None}
        self.assertIn(task['id'], {r['id'] for r in combine([task], rows)})

    def test_activity_ids_are_stable_when_ai_item_order_changes(self):
        items = [{'title': title, 'task_status': 'optional', 'deadline_kind': 'registration',
                  'deadline': '2026-11-20'} for title in ('로봇 공모전', '탐구 캠프')]
        before = {r['title']: r['id'] for r in self.collect(items)}
        after = {r['title']: r['id'] for r in self.collect(list(reversed(items)))}
        self.assertEqual(before, after)

    def test_repeated_instruction_with_named_ai_answers_does_not_duplicate_source_sections(self):
        p = self.post('1. 로봇 공모전 신청\n희망자는 신청하세요.\n접수기간: 2026.11.1.~2026.11.12.\n'
                      '2. 탐구 캠프 신청\n희망자는 신청하세요.\n접수기간: 2026.11.1.~2026.11.25.')
        items = [{'title': title, 'task_status': 'optional', 'deadline_kind': 'registration',
                  'task_evidence': '희망자는 신청하세요.', 'task_evidence_source': 'post'}
                 for title in ('로봇 공모전 신청', '탐구 캠프 신청')]
        rows = self.collect(items, p)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['analyzed'] for row in rows))
        self.assertEqual({row['nextDeadline'] for row in rows}, {'2026-11-12', '2026-11-25'})

    def test_pdf_sections_are_separate_activities_with_page_sources(self):
        p = self.post('첨부 안내를 확인하세요.')
        p['attachments'] = [{'file_id': 'f', 'pages': [{'page': 2, 'text':
            '1. 로봇 공모전 신청\n희망자는 신청하세요.\n접수기간: 2026.11.1.~2026.11.12.\n'
            '2. 탐구 캠프 신청\n희망자는 신청하세요.\n접수기간: 2026.11.1.~2026.11.25.'}]}]
        rows = self.collect(post=p)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['dates'][0]['source'] == 'pdf:f:2' for row in rows))


if __name__ == "__main__":
    unittest.main()
