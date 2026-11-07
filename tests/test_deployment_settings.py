import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.fernet import Fernet
from web_settings import Settings


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


if __name__ == '__main__':
    unittest.main()
