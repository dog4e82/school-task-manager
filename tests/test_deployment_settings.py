import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.fernet import Fernet
from web_settings import Settings, google_config_fingerprints


class DeploymentSettingsTests(unittest.TestCase):
    def settings(self, extra):
        with TemporaryDirectory() as directory:
            env={"APP_DATA_DIR":directory,"GOOGLE_WEB_CLIENT_FILE":str(Path(directory)/"absent.json"),
                 "APP_TOKEN_KEY":Fernet.generate_key().decode(),**extra}
            with patch.dict(os.environ,env,clear=True),patch("web_settings.load_dotenv"):
                return Settings.load()

    def test_render_uses_its_real_public_origin_without_a_guessed_domain(self):
        result=self.settings({"RENDER_EXTERNAL_URL":"https://actual-domain.onrender.com",
                              "DATABASE_URL":"postgresql://test:synthetic@db.example.invalid/moa?sslmode=require"})
        self.assertEqual(result.callback,"https://actual-domain.onrender.com/auth/callback")
        self.assertTrue(result.secure)

    def test_free_render_cannot_silently_lose_records_in_temporary_sqlite(self):
        with self.assertRaisesRegex(ValueError,"DATABASE_URL"):
            self.settings({"RENDER_EXTERNAL_URL":"https://actual-domain.onrender.com"})

    def test_invalid_database_config_does_not_echo_its_secret(self):
        try:
            self.settings({"DATABASE_URL":"https://private-user:private-password@db.example.invalid"})
        except ValueError as error:
            self.assertNotIn("private-password",str(error))
        else:
            self.fail("Invalid database configuration accepted")

    def test_local_sqlite_remains_available_without_hosted_database(self):
        result=self.settings({})
        self.assertFalse(result.database_url)
        self.assertEqual(result.callback,"http://127.0.0.1:8000/auth/callback")

    def test_manual_paste_of_quoted_oauth_values_removes_only_outer_quotes(self):
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                result=self.settings({'GOOGLE_WEB_CLIENT_ID':f' {quote}test.apps.googleusercontent.com{quote} ',
                                      'GOOGLE_WEB_CLIENT_SECRET':f' {quote}synthetic-secret{quote} '})
                self.assertEqual(result.client_id,'test.apps.googleusercontent.com')
                self.assertEqual(result.client_secret,'synthetic-secret')

    def test_google_secret_line_break_rejected_without_echoing_value(self):
        with self.assertRaises(ValueError) as error:
            self.settings({'GOOGLE_WEB_CLIENT_ID':'test.apps.googleusercontent.com',
                           'GOOGLE_WEB_CLIENT_SECRET':'synthetic-secret\nsecond-line'})
        self.assertNotIn('synthetic-secret',str(error.exception))

    def test_config_markers_require_private_key_and_identify_which_value_changed(self):
        original=google_config_fingerprints('synthetic-id','synthetic-secret','synthetic-key')
        changed=google_config_fingerprints('synthetic-id','other-secret','synthetic-key')
        self.assertEqual(original['client_id'],changed['client_id'])
        self.assertEqual(original['encryption_key'],changed['encryption_key'])
        self.assertNotEqual(original['client_secret'],changed['client_secret'])
        other_key=google_config_fingerprints('synthetic-id','synthetic-secret','other-key')
        self.assertNotEqual(original['encryption_key'],other_key['encryption_key'])
        self.assertNotIn('synthetic-secret',str(original))


if __name__ == '__main__':
    unittest.main()
