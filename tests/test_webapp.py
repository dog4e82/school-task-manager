import json
import sqlite3
import time
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials
from requests import Request as TokenRequest, Response

from classroom import READ_SCOPES, SYNC_SCOPES
from webapp import WEB_SCOPES, create_app
from web_settings import Settings
from web_store import Store


def credentials(label):
    return {"token": "private-access-"+label, "refresh_token": "private-refresh-"+label,
            "token_uri": "https://oauth2.googleapis.com/token", "client_id": "test.apps.googleusercontent.com",
            "client_secret": "private-client-secret", "scopes": READ_SCOPES, "expiry": "2050-01-01T00:00:00Z"}


def snapshot(label):
    return {"fetched_at": "2026-11-06T00:00:00Z", "complete": True,
            "courses": [{"id": label, "name": "private-course-"+label}],
            "assignments": [{"id": "post-"+label, "course_id": label, "course_name": "private-course-"+label,
                             "source": "coursework", "title": "private-task-"+label, "text": "보고서를 제출하세요.",
                             "due_at": "2026-11-15T23:59:00+09:00", "original_url": "https://classroom.google.com/"+label,
                             "raw": {"creationTime": "2026-11-01T00:00:00Z"}}], "announcements": [], "materials": []}


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.settings = Settings("http://127.0.0.1:8000", Path(self.temp.name), Fernet.generate_key().decode(),
                                 "test.apps.googleusercontent.com", "private-client-secret", "https://example.invalid", "private-baze-key")
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, base_url=self.settings.base_url, follow_redirects=False)
        self.client.__enter__()
        self.store = self.app.state.store
        self.a = self.store.save_user("subject-a", "a@example.invalid", "학생A", credentials("a"))
        self.b = self.store.save_user("subject-b", "b@example.invalid", "학생B", credentials("b"))
        self.store.save_snapshot(self.a, snapshot("a"))
        self.store.save_snapshot(self.b, snapshot("b"))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def login(self, user):
        token = self.store.create_session(user)
        self.client.cookies.set(self.settings.cookie, token)
        self.csrf = self.store.session(token)["csrf"]
        return {"X-CSRF-Token": self.csrf, "Origin": self.settings.base_url}

    def test_anonymous_home_does_not_include_existing_school_data(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Google로 Classroom", response.text)
        self.assertNotIn("private-course", response.text)
        self.assertEqual(self.client.get("/api/data").status_code, 401)
        self.assertEqual(self.client.get("/app").headers["location"], "/")

    def test_each_account_only_receives_its_own_snapshot(self):
        self.login(self.a)
        first = self.client.get("/api/data")
        self.assertIn("private-course-a", first.text)
        self.assertNotIn("private-course-b", first.text)
        self.login(self.b)
        second = self.client.get("/api/data")
        self.assertIn("private-course-b", second.text)
        self.assertNotIn("private-course-a", second.text)

    def test_personal_record_is_owner_scoped_and_requires_csrf(self):
        headers = self.login(self.a)
        item = self.client.get("/api/data").json()["schedule"][0]["id"]
        self.assertEqual(self.client.post("/api/personal", json={"item_id": item, "note": "private-note"}).status_code, 403)
        self.assertEqual(self.client.post("/api/personal", json={"item_id": item, "note": "private-note", "completed": True}, headers=headers).status_code, 200)
        self.assertIn("private-note", self.client.get("/app").text)
        self.login(self.b)
        self.assertNotIn("private-note", self.client.get("/app").text)
        self.assertEqual(self.client.post("/api/personal", json={"item_id": item, "completed": True}, headers={"X-CSRF-Token": self.csrf}).status_code, 404)

    def test_cross_origin_and_old_account_csrf_cannot_write(self):
        old = self.login(self.a)
        self.login(self.b)
        self.assertEqual(self.client.post("/api/logout", headers=old).status_code, 403)
        self.assertEqual(self.client.post("/api/logout", headers={"X-CSRF-Token": self.csrf, "Origin": "https://evil.invalid"}).status_code, 403)

    def test_private_credentials_never_reach_browser_or_plaintext_database(self):
        self.login(self.a)
        response = self.client.get("/app")
        for value in ("private-access-a", "private-refresh-a", "private-client-secret", "private-baze-key"):
            self.assertNotIn(value, response.text)
        with self.store.db() as db:
            encrypted = db.execute("SELECT credentials FROM users WHERE id=?", (self.a,)).fetchone()[0]
        self.assertNotIn(b"private-access-a", encrypted)
        self.assertEqual(self.store.decrypt(encrypted)["token"], "private-access-a")
        self.assertIn("no-store", response.headers["cache-control"])

    def test_server_never_serves_local_secret_or_export_files(self):
        for url in ("/credentials.json", "/credentials.web.json", "/.env", "/.local/classroom-ui.html", "/assets/app.js", "/assets/../credentials.json"):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_foreign_job_is_not_visible(self):
        job = self.store.new_job(self.a, "sync", "2026-11-06")
        self.login(self.b)
        self.assertEqual(self.client.get("/api/jobs/"+job).status_code, 404)
        self.assertIsNone(self.client.get("/api/jobs/latest").json()["job"])

    def test_google_error_does_not_echo_credentials(self):
        self.login(self.a)
        with patch("webapp.build", side_effect=RuntimeError("private-access-a private-refresh-a")):
            response = self.client.get("/api/courses")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("private-", response.text)

    def test_sync_rechecks_course_membership_before_reading_posts(self):
        headers = self.login(self.a)
        service = Mock()
        service.courses.return_value.list.return_value.execute.return_value = {"courses": [{"id": "a", "name": "A"}]}
        with patch("webapp.build", return_value=service), patch("webapp.collect_snapshot") as collect, patch.object(self.app.state.executor, "submit", side_effect=lambda fn,*args: fn(*args)):
            response = self.client.post("/api/sync", json={"course_ids": ["b"]}, headers=headers)
        self.assertEqual(response.status_code, 202)
        collect.assert_not_called()
        job = self.client.get("/api/jobs/"+response.json()["job_id"]).json()
        self.assertEqual(job["status"], "failed")
        self.assertEqual(self.store.snapshot(self.a)["courses"][0]["id"], "a")

    def test_reading_dashboard_never_generates_analysis(self):
        self.login(self.a)
        with patch("webapp.Client") as client:
            self.assertEqual(self.client.get("/app").status_code, 200)
            self.assertEqual(self.client.get("/api/data").status_code, 200)
        client.assert_not_called()

    def test_ai_requires_operator_enable_and_user_consent_and_fixed_model(self):
        headers = self.login(self.a)
        self.assertEqual(self.client.post("/api/analyze", json={"consent": True}, headers=headers).status_code, 503)
        self.settings.ai_enabled = True
        self.assertEqual(self.client.post("/api/analyze", json={"consent": False}, headers=headers).status_code, 400)
        self.assertEqual(self.client.post("/api/analyze", json={"consent": True, "model": "other"}, headers=headers).status_code, 422)

    def test_delete_own_account_revokes_and_removes_only_own_data(self):
        headers = self.login(self.a)
        directory = Path(self.temp.name) / "users" / self.a
        directory.mkdir(parents=True)
        (directory / "sample.txt").write_text("private cached page")
        with patch("webapp.requests.post", return_value=Mock(status_code=200)) as revoke:
            response = self.client.delete("/api/account", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(revoke.call_args.args[0], "https://oauth2.googleapis.com/revoke")
        self.assertFalse(directory.exists())
        self.assertIsNone(self.store.get_user(self.a))
        self.assertIsNotNone(self.store.get_user(self.b))
        self.assertEqual(self.client.get("/api/data").status_code, 401)

    def test_oauth_state_browser_binding_expiry_and_single_use(self):
        state,binding = self.store.begin_oauth({"verifier": "private-verifier"})
        self.assertIsNone(self.store.consume_oauth(state,"different-browser"))
        self.assertEqual(self.store.consume_oauth(state,binding)["verifier"],"private-verifier")
        self.assertIsNone(self.store.consume_oauth(state,binding))
        state,binding = self.store.begin_oauth({})
        with self.store.db() as db:
            db.execute("UPDATE oauth_states SET expires=0")
        self.assertIsNone(self.store.consume_oauth(state,binding))

    def test_invalid_oauth_callback_never_exchanges_token(self):
        with patch("webapp.Flow") as flow:
            response = self.client.get("/auth/callback?state=forged&code=private-code")
        self.assertIn("state_expired", response.headers["location"])
        self.assertNotIn("private-code", response.text)
        flow.from_client_config.assert_not_called()

    def test_real_authorization_url_contains_pkce_nonce_and_minimal_scopes(self):
        response=self.client.get('/auth/google')
        query=parse_qs(urlsplit(response.headers['location']).query)
        self.assertEqual(query['redirect_uri'],[self.settings.callback])
        self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertGreater(len(query['code_challenge'][0]),30)
        self.assertTrue(query['nonce'][0])
        self.assertNotIn('code_verifier',query)
        self.assertNotIn('https://www.googleapis.com/auth/drive.readonly',query['scope'][0].split())
        pdf=self.client.get('/auth/google?pdf=1')
        pdf_query=parse_qs(urlsplit(pdf.headers['location']).query)
        self.assertIn('https://www.googleapis.com/auth/drive.readonly',pdf_query['scope'][0].split())

    def test_oauth_uses_pkce_nonce_and_verified_identity(self):
        flows=[]
        def factory(config, scopes, state, code_verifier):
            flow=Mock()
            flow.credentials=Credentials.from_authorized_user_info(credentials("oauth"))
            flow.oauth2session.token={"id_token":"private-id-token"}
            flow.authorization_url.return_value=("https://accounts.google.com/o/oauth2/auth?state="+state,state)
            flows.append((flow,state,code_verifier))
            return flow
        with patch("webapp.Flow.from_client_config",side_effect=factory),patch("webapp.id_token.verify_oauth2_token") as verify:
            response=self.client.get("/auth/google")
            self.assertEqual(response.status_code,303)
            first,state,verifier=flows[0]
            self.assertGreater(len(verifier),42)
            nonce=first.authorization_url.call_args.kwargs["nonce"]
            verify.return_value={"sub":"new-subject","email":"new@example.invalid","name":"새 학생","email_verified":True,"nonce":nonce}
            response=self.client.get("/auth/callback?state="+state+"&code=private-code")
        self.assertEqual(response.headers["location"],"/setup")
        self.assertEqual(flows[1][2],verifier)
        self.assertIn("HttpOnly",response.headers["set-cookie"])
        self.assertNotIn("private-access",response.text)
        self.assertEqual(self.client.get("/setup").status_code,200)

    def test_nonce_mismatch_rejects_login(self):
        state,binding=self.store.begin_oauth({"verifier":"v","nonce":"expected","scopes":READ_SCOPES})
        self.client.cookies.set("moa_oauth",binding,path="/auth")
        flow=Mock(oauth2session=Mock(token={"id_token":"private"}))
        with patch("webapp.Flow.from_client_config",return_value=flow),patch("webapp.id_token.verify_oauth2_token",return_value={"sub":"attacker","nonce":"wrong","email_verified":True}):
            response=self.client.get("/auth/callback?state="+state+"&code=c")
        self.assertIn("oauth_identity_failed",response.headers["location"])
        self.assertIsNone(self.client.cookies.get(self.settings.cookie))

    def test_oauth_token_failure_has_safe_code_without_exception_secrets(self):
        state,binding=self.store.begin_oauth({"verifier":"v","nonce":"expected","scopes":READ_SCOPES})
        self.client.cookies.set("moa_oauth",binding,path="/auth")
        flow=Mock()
        flow.fetch_token.side_effect=ValueError("private-client-secret private-code private-token")
        with patch("webapp.Flow.from_client_config",return_value=flow),self.assertLogs("moa",level="WARNING") as logs:
            response=self.client.get("/auth/callback?state="+state+"&code=private-code")
        self.assertEqual(response.headers["location"],"/?error=oauth_token_failed")
        page=self.client.get(response.headers["location"]).text
        self.assertIn("LOGIN-TOKEN",page)
        self.assertNotIn("private-",page+str(logs.output)+response.text)
        self.assertIn("oauth_callback_failed:token:ValueError",str(logs.output))
        self.assertIsNone(self.client.cookies.get(self.settings.cookie))
        self.assertIsNone(self.store.consume_oauth(state,binding))

    def test_real_token_parser_with_extra_grant_completes_web_login(self):
        start=self.client.get("/auth/google")
        query=parse_qs(urlsplit(start.headers["location"]).query)
        granted=WEB_SCOPES+SYNC_SCOPES
        token=Response()
        token.status_code=200
        token.request=TokenRequest("POST","https://oauth2.googleapis.com/token",data="code=private-code").prepare()
        token._content=json.dumps({"access_token":"private-access-new", "refresh_token":"private-refresh-new",
            "id_token":"private-id-new", "token_type":"Bearer", "expires_in":3600,
            "scope":" ".join(granted)}).encode()
        claims={"sub":"new-real-parser", "email":"new@example.invalid", "email_verified":True,
                "nonce":query["nonce"][0]}
        with patch("requests_oauthlib.OAuth2Session.request",return_value=token),patch("webapp.id_token.verify_oauth2_token",return_value=claims):
            response=self.client.get("/auth/callback",params={"state":query["state"][0],"code":"private-code"})
        self.assertEqual(response.headers["location"],"/setup")
        self.assertEqual(self.client.get("/setup").status_code,200)
        session=self.store.session(self.client.cookies.get(self.settings.cookie))
        self.assertIsNotNone(session)
        saved=self.store.get_user(session["user_id"])["credentials"]
        self.assertIn("https://www.googleapis.com/auth/drive.readonly",saved["scopes"])
        self.assertNotIn("private-access-new",response.text)

    def test_real_token_parser_missing_scope_never_creates_account_session(self):
        start=self.client.get("/auth/google")
        query=parse_qs(urlsplit(start.headers["location"]).query)
        token=Response()
        token.status_code=200
        token.request=TokenRequest("POST","https://oauth2.googleapis.com/token",data="code=private-code").prepare()
        token._content=json.dumps({"access_token":"private-access-new", "token_type":"Bearer", "expires_in":3600,
            "scope":" ".join(WEB_SCOPES+READ_SCOPES[:-1])}).encode()
        with patch("requests_oauthlib.OAuth2Session.request",return_value=token),patch("webapp.id_token.verify_oauth2_token") as verify:
            response=self.client.get("/auth/callback",params={"state":query["state"][0],"code":"private-code"})
        self.assertEqual(response.headers["location"],"/?error=oauth_permissions_failed")
        verify.assert_not_called()
        self.assertIsNone(self.client.cookies.get(self.settings.cookie))

    def test_daily_generation_reservation_is_atomic_and_per_user(self):
        job=self.store.new_job(self.a,"analyze","2026-11-06",3)
        self.store.finish_job(self.a,job,"done","done")
        with self.assertRaisesRegex(ValueError,"daily_limit"):
            self.store.new_job(self.a,"analyze","2026-11-06",1)
        self.assertIsNotNone(self.store.new_job(self.b,"analyze","2026-11-06",3))

    def test_global_generation_cap_is_shared_across_accounts(self):
        job=self.store.new_job(self.a,"analyze","2026-11-06",3,global_limit=3)
        self.store.finish_job(self.a,job,"done","done")
        with self.assertRaisesRegex(ValueError,"global_limit"):
            self.store.new_job(self.b,"analyze","2026-11-06",1,global_limit=3)

    def test_secure_cookie_is_set_for_https(self):
        self.settings.base_url="https://127.0.0.1:8000"
        self.login(self.a)
        self.assertTrue(self.settings.secure)
        response=self.client.get('/auth/google')
        self.assertIn("Secure",response.headers['set-cookie'])


if __name__ == "__main__":
    unittest.main()
