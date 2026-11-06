import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from main import BazeError
from notice_ai import (AnalysisError, Cache, DEFAULT_MODEL, MAX_CHARS,
                       grounded_date, prepare, run_analysis, validate)


TEXT = "보고서를 2026년 11월 13일까지 제출하세요."


def post(text=TEXT, ident="1", course="c", created="2026-11-01T00:00:00Z"):
    return {"id": ident, "course_id": course, "source": "announcement", "title": "안내",
            "text": text, "due_at": None, "raw": {"creationTime": created}}


def jobs(posts=None, model=DEFAULT_MODEL, with_context=False):
    return prepare({"assignments": [], "announcements": posts or [post()]}, model, "https://example.invalid", with_context=with_context)


def item(evidence=TEXT, status="required", due="2026-11-13", due_quote=TEXT):
    return {"title": "보고서", "task_status": status, "task_evidence": evidence,
            "deadline_status": "confirmed" if due else "unknown", "deadline": due,
            "deadline_evidence": due_quote}


def answer(items=None, relations=None):
    return json.dumps({"items": items if items is not None else [item()], "relations": relations or []}, ensure_ascii=False)


def client(response=None):
    obj = Mock(key="fake-private-api-key")
    obj.models.return_value = {"data": [{"id": DEFAULT_MODEL, "type": "llm", "pricing": {}}]}
    obj.balance.return_value = {"total": {"remaining": 100}}
    obj.request.return_value = response or {
        "choices": [{"finish_reason": "stop", "message": {"content": answer()}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 60, "total_tokens": 160}}
    return obj


class GroundingTests(unittest.TestCase):
    def validate_item(self, entry, text=TEXT):
        return validate(answer([entry]), jobs([post(text)])[0]["payload"])["items"][0]

    def test_explicit_deadline_supported_by_exact_quote(self):
        result = self.validate_item(item())
        self.assertEqual(result["task_status"], "required")
        self.assertEqual(result["deadline"], "2026-11-13")
        self.assertFalse(result["review_required"])

    def test_publication_date_never_becomes_deadline(self):
        text = "과학 보고서를 제출하세요. 마감은 추후 공지합니다. 참고 영상은 2026년 11월 10일 공개됩니다."
        result = self.validate_item(item(text, due="2026-11-10", due_quote=text), text)
        self.assertIsNone(result["deadline"])
        self.assertEqual(result["deadline_status"], "unknown")

    def test_reference_cannot_receive_deadline_even_with_due_quote(self):
        result = self.validate_item(item(status="reference"))
        self.assertIsNone(result["deadline"])
        self.assertEqual(result["task_status"], "unknown")

    def test_forged_quote_cannot_confirm_obligation(self):
        result = self.validate_item(item(evidence="반드시 제출하세요."))
        self.assertEqual(result["task_status"], "unknown")
        self.assertIsNone(result["task_evidence"])

    def test_optional_conditional_and_negated_instructions_not_required(self):
        for text in ("보고서는 선택 활동입니다.", "발표자만 자료를 제출하세요.", "보고서는 제출하지 마세요."):
            result = self.validate_item(item(text, due=None), text)
            self.assertEqual(result["task_status"], "unknown")

    def test_yearless_relative_and_invalid_dates_not_confirmed(self):
        for quote in ("11월 13일까지 제출하세요.", "내일까지 제출하세요.", "2026년 2월 30일까지 제출하세요."):
            self.assertFalse(grounded_date("2026-11-13", quote))

    def test_unrelated_due_clause_does_not_validate_event_date(self):
        self.assertFalse(grounded_date("2026-11-10", "보고서 제출 기한은 추후 공지. 영상은 2026년 11월 10일 공개됩니다."))

    def test_code_fenced_json_supported_but_prose_is_rejected(self):
        payload = jobs()[0]["payload"]
        self.assertEqual(len(validate("```json\n" + answer() + "\n```", payload)["items"]), 1)
        with self.assertRaises(AnalysisError):
            validate("분석 결과입니다: " + answer(), payload)

    def test_cross_course_relations_rejected(self):
        prepared = jobs([post(ident="old", course="other"), post(ident="new", created="2026-11-02T00:00:00Z")], with_context=True)[0]
        relation = {"target_key": "other:announcement:old", "type": "deadline_change", "evidence": TEXT}
        self.assertEqual(validate(answer(relations=[relation]), prepared["payload"])["relations"], [])

    def test_same_course_previous_candidate_relation_kept_for_review(self):
        prepared = jobs([post(ident="old"), post(ident="new", created="2026-11-02T00:00:00Z")], with_context=True)[0]
        relation = {"target_key": "c:announcement:old", "type": "deadline_change", "evidence": TEXT}
        result = validate(answer(relations=[relation]), prepared["payload"])
        self.assertEqual(result["relations"], [relation])
        self.assertTrue(result["relations_review_required"])

    def test_official_deadline_conflict_flagged_without_modifying_input(self):
        prepared = jobs()[0]
        prepared["payload"]["current"]["classroom_due_at"] = "2026-11-14T23:59:00+09:00"
        result = validate(answer(), prepared["payload"])
        self.assertIn("classroom_deadline_conflict", result["items"][0]["review_flags"])
        self.assertEqual(prepared["payload"]["current"]["classroom_due_at"], "2026-11-14T23:59:00+09:00")


class CacheAndCallTests(unittest.TestCase):
    def test_default_payload_excludes_other_posts(self):
        prepared = jobs([post(ident="old"), post(ident="new", created="2026-11-02T00:00:00Z")])
        self.assertEqual(prepared[0]["payload"]["candidates"], [])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.cache = Cache(Path(self.temp.name) / "analysis.sqlite3")
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.cache.close()
        self.temp.cleanup()

    def test_second_run_reuses_persistent_result_without_network(self):
        obj = client()
        first = run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        second = run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        self.assertEqual(first["succeeded"], 1)
        self.assertEqual(second["cached"], 1)
        obj.request.assert_called_once()
        self.assertEqual(obj.models.call_count, 1)

    def test_changed_input_or_model_has_new_fingerprint(self):
        before = jobs()[0]["key"]
        self.assertNotEqual(before, jobs([post(TEXT + "変更")])[0]["key"])
        self.assertNotEqual(before, jobs(model="another-model")[0]["key"])
        self.assertEqual(before, jobs()[0]["key"])

    def test_limit_caps_generation_and_reports_remaining(self):
        prepared = jobs([post(ident=str(i)) for i in range(5)])
        result = run_analysis(client(), self.cache, prepared, DEFAULT_MODEL, limit=2)
        self.assertEqual(result["calls"], 2)
        self.assertEqual(result["pending"], 3)

    def test_preflight_balance_failure_makes_no_generation(self):
        obj = client()
        obj.balance.side_effect = BazeError("unavailable")
        with self.assertRaises(BazeError):
            run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        obj.request.assert_not_called()

    def test_network_failure_not_retried_next_run_without_explicit_flag(self):
        obj = client()
        obj.request.side_effect = BazeError("timeout")
        first = run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        second = run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        self.assertEqual(first["failed"], 1)
        self.assertEqual(second["skipped"], 1)
        obj.request.assert_called_once()
        self.assertEqual(obj.balance.call_count, 2)

    def test_explicit_failed_retry_can_make_one_more_call(self):
        obj = client()
        obj.request.side_effect = BazeError("timeout")
        run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        obj = client()
        result = run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL, retry_failed=True)
        self.assertEqual(result["succeeded"], 1)
        obj.request.assert_called_once()

    def test_truncated_output_stays_invalid_without_automatic_retry(self):
        obj = client({"choices": [{"finish_reason": "length", "message": {"content": answer()}}], "usage": {"total_tokens": 2048}})
        result = run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(self.cache.get(jobs()[0]["key"])["status"], "invalid")
        run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL)
        obj.request.assert_called_once()

    def test_dry_run_and_oversize_never_send_source(self):
        obj = client()
        run_analysis(obj, self.cache, jobs(), DEFAULT_MODEL, dry_run=True)
        result = run_analysis(obj, self.cache, jobs([post("x" * (MAX_CHARS + 1))]), DEFAULT_MODEL)
        self.assertEqual(result["skipped"], 1)
        obj.models.assert_not_called()
        obj.request.assert_not_called()

    def test_atomic_claim_blocks_duplicate_active_request(self):
        job = jobs()[0]
        self.assertTrue(self.cache.claim(job, DEFAULT_MODEL))
        self.assertFalse(self.cache.claim(job, DEFAULT_MODEL, retry_failed=True))

    def test_missing_billing_stored_as_missing_not_inferred(self):
        run_analysis(client(), self.cache, jobs(), DEFAULT_MODEL)
        record = self.cache.get(jobs()[0]["key"])
        self.assertIsNone(record["metrics"]["billing"])


if __name__ == "__main__":
    unittest.main()
