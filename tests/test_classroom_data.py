import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from googleapiclient.errors import HttpError
from httplib2 import Response

import classroom
from classroom_data import all_pages, collect_snapshot, deadline, normalize, sort_tasks
from classroom_errors import error_reason, operation


class DataTests(unittest.TestCase):
    def test_one_denied_course_does_not_hide_other_work_or_notices(self):
        service = Mock()
        denied = HttpError(Response({"status": "403"}), b'{"error":{"message":"The caller does not have permission"}}')
        service.courses.return_value.courseWork.return_value.list.return_value.execute.side_effect = [
            denied, {"courseWork": [{"id": "task"}]},
        ]
        service.courses.return_value.announcements.return_value.list.return_value.execute.side_effect = [
            {"announcements": [{"id": "notice1"}]}, {"announcements": [{"id": "notice2"}]},
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            snapshot = collect_snapshot(service, [{"id": "teacher"}, {"id": "student"}])
        self.assertFalse(snapshot["complete"])
        self.assertEqual([a["id"] for a in snapshot["assignments"]], ["task"])
        self.assertEqual(len(snapshot["announcements"]), 2)
        self.assertEqual(snapshot["failures"][0]["resource"], "courseWork")

    def test_scope_failure_still_aborts_collection(self):
        service = Mock()
        error = HttpError(Response({"status": "403"}), b'{"error":{"message":"Request had insufficient authentication scopes."}}')
        service.courses.return_value.courseWork.return_value.list.return_value.execute.side_effect = error
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(HttpError):
            collect_snapshot(service, [{"id": "c"}])

    def test_error_details_do_not_leak_server_message_or_url(self):
        error = HttpError(Response({"status": "403"}), b'{"error":{"message":"private-token","details":[{"reason":"ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}', uri="https://classroom.googleapis.com/v1/courses/private-id/courseWork")
        self.assertEqual(error_reason(error), "ACCESS_TOKEN_SCOPE_INSUFFICIENT")
        self.assertEqual(operation(error), "courses.courseWork.list")

    def test_partial_sync_returns_distinct_exit_status(self):
        with patch.object(classroom, "credentials"), patch.object(classroom, "build"), patch.object(classroom, "list_courses", return_value=[{"id": "c"}]), patch.object(classroom, "sync", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(classroom.main(["sync"]), 2)

    def test_late_permission_denial_discards_that_resources_partial_pages(self):
        service = Mock()
        denied = HttpError(Response({"status": "403"}), b'{"error":{"message":"The caller does not have permission"}}')
        service.courses.return_value.courseWork.return_value.list.return_value.execute.side_effect = [
            {"courseWork": [{"id": "partial"}], "nextPageToken": "second"}, denied,
        ]
        service.courses.return_value.announcements.return_value.list.return_value.execute.return_value = {}
        with contextlib.redirect_stdout(io.StringIO()):
            snapshot = collect_snapshot(service, [{"id": "c"}])
        self.assertEqual(snapshot["assignments"], [])
        self.assertFalse(snapshot["complete"])

    def test_all_work_pages_even_empty_intermediate(self):
        resource = Mock()
        resource.list.return_value.execute.side_effect = [
            {"courseWork": [{"id": "a"}], "nextPageToken": "two"},
            {"nextPageToken": "three"}, {"courseWork": [{"id": "b"}]},
        ]
        result = all_pages(resource, "courseWork", courseId="course")
        self.assertEqual([r["id"] for r in result], ["a", "b"])
        self.assertEqual(resource.list.call_args.kwargs["pageToken"], "three")
        self.assertEqual(resource.list.call_args.kwargs["courseId"], "course")

    def test_utc_due_time_crosses_into_next_korean_day(self):
        raw = {"dueDate": {"year": 2026, "month": 11, "day": 5}, "dueTime": {"hours": 15}}
        self.assertEqual(deadline(raw), "2026-11-06T00:00:00+09:00")

    def test_empty_time_is_midnight_utc(self):
        raw = {"dueDate": {"year": 2026, "month": 11, "day": 5}, "dueTime": {}}
        self.assertEqual(deadline(raw), "2026-11-05T09:00:00+09:00")

    def test_missing_or_invalid_due_is_not_invented(self):
        for raw in ({}, {"dueDate": {"year": 2026, "month": 11, "day": 5}},
                    {"dueDate": {"year": 2026, "month": 2, "day": 30}, "dueTime": {}}):
            self.assertIsNone(deadline(raw))

    def test_announcement_date_does_not_become_deadline(self):
        raw = {"id": "a", "text": "참고 영상은 2026년 11월 10일 공개됩니다."}
        item = normalize(raw, {"id": "c"}, "announcement")
        self.assertIsNone(item["due_at"])
        self.assertEqual(item["deadline_status"], "unknown")
        self.assertEqual(item["task_status"], "unknown")
        self.assertEqual(item["raw"], raw)

    def test_undated_last_and_unrelated_courses_not_read(self):
        service = Mock()
        service.courses.return_value.courseWork.return_value.list.return_value.execute.return_value = {
            "courseWork": [{"id": "no-date"}, {"id": "due", "dueDate": {"year": 2026, "month": 11, "day": 5}, "dueTime": {}}]}
        service.courses.return_value.announcements.return_value.list.return_value.execute.return_value = {
            "announcements": [{"id": "post", "text": "Original notice"}]}
        with contextlib.redirect_stdout(io.StringIO()):
            snapshot = collect_snapshot(service, [{"id": "selected", "name": "Science"}])
        self.assertEqual([i["id"] for i in snapshot["assignments"]], ["due", "no-date"])
        self.assertEqual(snapshot["announcements"][0]["text"], "Original notice")
        self.assertEqual(service.courses.return_value.courseWork.return_value.list.call_args.kwargs["courseId"], "selected")

    def test_failed_collection_preserves_previous_snapshot(self):
        service = Mock()
        service.courses.return_value.courseWork.return_value.list.return_value.execute.side_effect = HttpError(Response({"status": "403"}), b'{}')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            selection, snapshot = root / "selected.json", root / "snapshot.json"
            selection.write_text('{"courses":[{"id":"c"}]}', encoding="utf-8")
            snapshot.write_text('previous result', encoding="utf-8")
            with patch.object(classroom, "SELECTION_FILE", selection), patch.object(classroom, "SNAPSHOT_FILE", snapshot), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(HttpError):
                    classroom.sync(service, [{"id": "c"}])
            self.assertEqual(snapshot.read_text(encoding="utf-8"), 'previous result')

    def test_tasks_reads_saved_data_without_authentication(self):
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(json.dumps({"fetched_at": "2026-11-05T00:00:00Z", "assignments": [], "announcements": []}), encoding="utf-8")
            with patch.object(classroom, "SNAPSHOT_FILE", snapshot), patch.object(classroom, "credentials") as auth, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(classroom.main(["tasks"]), 0)
                auth.assert_not_called()

    def test_sync_upgrades_scope_and_preserves_live_service(self):
        with patch.object(classroom, "credentials") as auth, patch.object(classroom, "build") as build, patch.object(classroom, "list_courses", return_value=[{"id": "c"}]), patch.object(classroom, "sync") as sync, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(classroom.main(["sync"]), 0)
            auth.assert_called_once_with(reauth=False, scopes=classroom.SYNC_SCOPES, upgrade=True)
            sync.assert_called_once_with(build.return_value, [{"id": "c"}], drive=build.return_value)
            self.assertEqual(build.return_value.close.call_count, 2)


if __name__ == "__main__":
    unittest.main()
