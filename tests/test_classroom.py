import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response

import classroom


class ClassroomTests(unittest.TestCase):
    def test_all_pages_including_empty_intermediate(self):
        service = Mock()
        request = service.courses.return_value.list.return_value
        request.execute.side_effect = [
            {"courses": [{"id": "a", "name": "Science"}], "nextPageToken": "next"},
            {"nextPageToken": "last"},
            {"courses": [{"id": "b", "name": "Math"}]},
        ]
        self.assertEqual([c["id"] for c in classroom.list_courses(service)], ["a", "b"])
        self.assertEqual(service.courses.return_value.list.call_args_list[1].kwargs,
                         {"pageSize": 100, "pageToken": "next"})
        self.assertEqual(request.execute.call_count, 3)

    def test_repeated_page_token_does_not_loop(self):
        service = Mock()
        service.courses.return_value.list.return_value.execute.return_value = {"nextPageToken": "repeat"}
        with self.assertRaises(classroom.ClassroomError):
            classroom.list_courses(service)

    def test_later_page_failure_does_not_return_partial_list(self):
        service = Mock()
        service.courses.return_value.list.return_value.execute.side_effect = [
            {"courses": [{"id": "a"}], "nextPageToken": "next"},
            HttpError(Response({"status": "403"}), b'{}'),
        ]
        with self.assertRaises(HttpError):
            classroom.list_courses(service)

    def test_cached_token_without_scope_requires_consent(self):
        creds = Mock()
        creds.has_scopes.return_value = False
        with patch.object(classroom, "TOKEN_FILE") as path, patch.object(classroom.Credentials, "from_authorized_user_file", return_value=creds), patch.object(classroom, "save_json") as save:
            path.exists.return_value = True
            with self.assertRaisesRegex(classroom.ClassroomError, "--reauth"):
                classroom.credentials()
            save.assert_not_called()

    def test_course_selection_is_validated(self):
        self.assertEqual(classroom.parse_selection("3,1,3", 3), [0, 2])
        self.assertEqual(classroom.parse_selection("all", 2), [0, 1])
        for value in ("0", "-1", "4", "abc", "1,", ""):
            with self.assertRaises(classroom.ClassroomError):
                classroom.parse_selection(value, 3)

    def test_only_selected_course_fields_saved(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "selected.json"
            courses = [{"id": "a", "name": "Science", "enrollmentCode": "private"},
                       {"id": "b", "name": "Math"}]
            with patch.object(classroom, "SELECTION_FILE", target), patch("builtins.input", return_value="2"), contextlib.redirect_stdout(io.StringIO()):
                classroom.choose_courses(courses)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")),
                             {"courses": [{"id": "b", "name": "Math"}]})

    def test_cancel_preserves_previous_selection(self):
        with patch("builtins.input", return_value=""), patch.object(classroom, "save_json") as save, contextlib.redirect_stdout(io.StringIO()):
            classroom.choose_courses([{"id": "a"}])
        save.assert_not_called()

    def test_missing_credentials_does_not_open_browser(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with patch.object(classroom, "CLIENT_FILE", missing), patch.object(classroom, "TOKEN_FILE", missing), patch.object(classroom, "InstalledAppFlow") as flow:
                with self.assertRaisesRegex(classroom.ClassroomError, "credentials.json"):
                    classroom.credentials()
                flow.from_client_config.assert_not_called()

    def test_cached_expired_credentials_are_refreshed(self):
        creds = Mock(expired=True, refresh_token="private-refresh", valid=True)
        creds.to_json.return_value = '{"token": "private-token"}'
        with patch.object(classroom, "TOKEN_FILE") as path, patch.object(classroom.Credentials, "from_authorized_user_file", return_value=creds), patch.object(classroom, "save_json") as save, patch.object(classroom, "InstalledAppFlow") as flow:
            path.exists.return_value = True
            self.assertIs(classroom.credentials(), creds)
            creds.refresh.assert_called_once()
            save.assert_called_once()
            flow.from_client_config.assert_not_called()

    def test_revoked_token_gives_safe_message(self):
        creds = Mock(expired=True, refresh_token="private-refresh")
        creds.refresh.side_effect = RefreshError("secret-server-body")
        with patch.object(classroom, "TOKEN_FILE") as path, patch.object(classroom.Credentials, "from_authorized_user_file", return_value=creds):
            path.exists.return_value = True
            with self.assertRaises(classroom.ClassroomError) as error:
                classroom.credentials()
        self.assertNotIn("secret", str(error.exception))
        self.assertIn("--reauth", str(error.exception))

    def test_http_error_body_and_tokens_not_printed(self):
        error = HttpError(Response({"status": "403"}), b'{"error":{"message":"private-token"}}')
        output = io.StringIO()
        with patch.object(classroom, "credentials", return_value=Mock()), patch.object(classroom, "build") as build, patch.object(classroom, "list_courses", side_effect=error), contextlib.redirect_stderr(output):
            self.assertEqual(classroom.main(["connect"]), 1)
        self.assertIn("403", output.getvalue())
        self.assertNotIn("private-token", output.getvalue())
        build.return_value.close.assert_called_once()

    def test_new_login_uses_loopback_and_clears_old_selection(self):
        creds = Mock(valid=True, granted_scopes=None)
        creds.to_json.return_value = '{"token": "private-token"}'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client, token, selection = (root / name for name in ("credentials.json", "token.json", "selection.json"))
            client.write_text('{"installed": {"client_id": "test"}}', encoding="utf-8")
            selection.write_text('{"courses":[{"id":"old-account"}]}', encoding="utf-8")
            with patch.object(classroom, "CLIENT_FILE", client), patch.object(classroom, "TOKEN_FILE", token), patch.object(classroom, "SELECTION_FILE", selection), patch.object(classroom, "SNAPSHOT_FILE", root / "snapshot.json"), patch.object(classroom.InstalledAppFlow, "from_client_config") as create, contextlib.redirect_stdout(io.StringIO()):
                create.return_value.run_local_server.return_value = creds
                classroom.credentials(reauth=True)
                kwargs = create.return_value.run_local_server.call_args.kwargs
                self.assertEqual(kwargs["host"], "127.0.0.1")
                self.assertNotIn("{url}", kwargs["authorization_prompt_message"])
                self.assertEqual(kwargs["timeout_seconds"], 180)
                self.assertFalse(selection.exists())
                self.assertTrue(token.exists())


if __name__ == "__main__":
    unittest.main()
