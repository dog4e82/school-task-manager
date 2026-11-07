"""Exercise the real OAuth token parser with mocked HTTP, without real secrets."""

import contextlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from requests import Request, Response

import classroom
from webapp import WEB_SCOPES, MissingLoginScopes, accept_granted_scopes


CONFIG = {"installed": {
    "client_id": "test.apps.googleusercontent.com", "client_secret": "fake-secret",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uris": ["http://localhost"],
}}
OLD_SCOPE = "https://www.googleapis.com/auth/classroom.coursework.me.readonly"
RETURNED_SCOPE = "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly"


def response(scopes):
    result = Response()
    result.status_code = 200
    result.request = Request("POST", "https://oauth2.googleapis.com/token", data="code=fake-code").prepare()
    result._content = json.dumps({
        "access_token": "fake-token", "refresh_token": "fake-refresh",
        "token_type": "Bearer", "expires_in": 3600, "scope": " ".join(scopes),
    }).encode()
    return result


class ScopeTests(unittest.TestCase):
    def exchange(self, requested, returned):
        flow = InstalledAppFlow.from_client_config(CONFIG, requested)
        with patch.object(flow.oauth2session, "request", return_value=response(returned)):
            flow.fetch_token(code="fake-code")
        return flow.credentials

    def test_original_scope_reproduces_reported_failure(self):
        requested = [OLD_SCOPE if s == RETURNED_SCOPE else s for s in classroom.READ_SCOPES]
        with patch.dict(os.environ):
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            with self.assertRaises(Warning):
                self.exchange(requested, classroom.READ_SCOPES)

    def test_requested_returned_scope_passes_real_token_parser(self):
        with patch.dict(os.environ):
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            creds = self.exchange(classroom.READ_SCOPES, classroom.READ_SCOPES)
        self.assertTrue(creds.has_scopes(classroom.READ_SCOPES))
        self.assertTrue(creds.valid)
        self.assertEqual(set(creds.granted_scopes), set(classroom.READ_SCOPES))

    def test_missing_announcement_scope_still_rejected(self):
        with patch.dict(os.environ):
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            with self.assertRaises(Warning):
                self.exchange(classroom.READ_SCOPES, classroom.READ_SCOPES[:-1])

    def test_scope_warning_keeps_saved_login_and_selection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client, token, selected, snapshot = (root / f for f in ("client.json", "token.json", "selected.json", "snapshot.json"))
            client.write_text(json.dumps(CONFIG), encoding="utf-8")
            for path in (token, selected, snapshot):
                path.write_text("previous state", encoding="utf-8")
            with patch.object(classroom, "CLIENT_FILE", client), patch.object(classroom, "TOKEN_FILE", token), patch.object(classroom, "SELECTION_FILE", selected), patch.object(classroom, "SNAPSHOT_FILE", snapshot), patch.object(classroom.InstalledAppFlow, "from_client_config") as create, contextlib.redirect_stdout(io.StringIO()):
                create.return_value.run_local_server.side_effect = Warning("fake-token")
                with self.assertRaises(classroom.ClassroomError) as error:
                    classroom.credentials(reauth=True, scopes=classroom.READ_SCOPES)
            self.assertNotIn("fake-token", str(error.exception))
            for path in (token, selected, snapshot):
                self.assertEqual(path.read_text(encoding="utf-8"), "previous state")


class WebScopeTests(unittest.TestCase):
    requested = WEB_SCOPES + classroom.READ_SCOPES
    extra = "https://www.googleapis.com/auth/drive.readonly"

    def exchange(self, granted, guard=True):
        flow = Flow.from_client_config({"web": CONFIG["installed"]}, self.requested)
        if guard:
            accept_granted_scopes(flow, self.requested)
        with patch.object(flow.oauth2session, "request", return_value=response(granted)):
            flow.fetch_token(code="fake-code")
        return flow.credentials

    def test_previous_pdf_grant_reproduces_unguarded_parser_failure(self):
        with patch.dict(os.environ):
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            with self.assertRaises(Warning):
                self.exchange(self.requested + [self.extra], guard=False)

    def test_superset_grant_passes_and_preserves_actual_scopes(self):
        with patch.dict(os.environ):
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            creds = self.exchange(self.requested + [self.extra])
        self.assertTrue(creds.valid)
        self.assertTrue(creds.has_scopes(self.requested))
        self.assertIn(self.extra, creds.granted_scopes)
        self.assertIn(self.extra, creds.scopes)

    def test_exact_grant_passes(self):
        self.assertTrue(self.exchange(self.requested).valid)

    def test_missing_required_grant_rejected_even_when_global_relax_is_set(self):
        with patch.dict(os.environ, {"OAUTHLIB_RELAX_TOKEN_SCOPE": "1"}):
            with self.assertRaises(MissingLoginScopes):
                self.exchange(self.requested[:-1] + [self.extra])

    def test_absent_scope_not_treated_as_requested_scope(self):
        flow = Flow.from_client_config({"web": CONFIG["installed"]}, self.requested)
        accept_granted_scopes(flow, self.requested)
        token = response([])
        payload = token.json()
        del payload["scope"]
        token._content = json.dumps(payload).encode()
        with patch.object(flow.oauth2session, "request", return_value=token):
            with self.assertRaises(MissingLoginScopes):
                flow.fetch_token(code="fake-code")


if __name__ == "__main__":
    unittest.main()
