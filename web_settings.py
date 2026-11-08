"""Explicit web OAuth configuration; never reuse the desktop OAuth client."""

import os
import json
import hashlib
import hmac
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent


def oauth_env_value(name):
    value = os.environ.get(name, "").strip()
    if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
        value = value[1:-1].strip()
    if '\n' in value or '\r' in value:
        raise ValueError(name + "에는 값만 한 줄로 입력하세요.")
    return value


def google_config_fingerprints(client_id, client_secret, token_key):
    """Private keyed comparison markers; never publish these in an endpoint."""
    return {name: hmac.new(token_key.encode(), b'moa/oauth-config/v1/' + name.encode() + b'\0' + value.encode(), hashlib.sha256).hexdigest()
            for name, value in [('client_id', client_id), ('client_secret', client_secret), ('encryption_key', 'key-check')]}


@dataclass
class Settings:
    base_url: str
    data_dir: Path
    token_key: str
    client_id: str = ""
    client_secret: str = ""
    baze_base: str = ""
    baze_key: str = ""
    ai_enabled: bool = False
    ai_daily_limit: int = 0
    ai_global_daily_limit: int = 0
    database_url: str = ""
    minimum_credits: int = 2000
    school_domain: str = ""

    @property
    def secure(self):
        return self.base_url.startswith("https://")

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    @property
    def callback(self):
        return self.base_url + "/auth/callback"

    @property
    def cookie(self):
        return "__Host-moa_session" if self.secure else "moa_session"

    def google_config(self):
        return {"web": {"client_id": self.client_id, "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.callback]}}

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
        base = (os.environ.get("APP_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
        parsed = urlsplit(base)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path
                or parsed.scheme not in ("http", "https")
                or (parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"))):
            raise ValueError("APP_BASE_URL은 HTTPS 주소 또는 로컬 테스트용 http://127.0.0.1:8000이어야 합니다.")
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if os.environ.get("RENDER_EXTERNAL_URL") and not database_url:
            raise ValueError("무료 Render 배포에는 DATABASE_URL을 설정하세요. 임시 SQLite에 개인 기록을 저장하지 않습니다.")
        if database_url and urlsplit(database_url).scheme not in ("postgres", "postgresql"):
            raise ValueError("DATABASE_URL에는 PostgreSQL 연결 주소를 설정하세요. 값은 출력하지 않습니다.")
        directory = Path(os.environ.get("APP_DATA_DIR") or ROOT / ".local" / "web").resolve()
        key = os.environ.get("APP_TOKEN_KEY", "").strip()
        if not key:
            if parsed.scheme == "https":
                raise ValueError("공개 서버의 APP_TOKEN_KEY를 설정하세요. 값을 로그나 채팅에 출력하지 마세요.")
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "token-encryption.key"
            if not path.exists():
                try:
                    with path.open("xb") as stream:
                        stream.write(Fernet.generate_key())
                except FileExistsError:
                    pass
            key = path.read_text(encoding="ascii").strip()
        try:
            Fernet(key.encode())
        except (ValueError, TypeError):
            raise ValueError("APP_TOKEN_KEY 형식이 올바르지 않습니다.") from None
        client_id = oauth_env_value("GOOGLE_WEB_CLIENT_ID")
        client_secret = oauth_env_value("GOOGLE_WEB_CLIENT_SECRET")
        client_path = Path(os.environ.get("GOOGLE_WEB_CLIENT_FILE") or ROOT / "credentials.web.json")
        if not client_id and not client_secret and client_path.exists():
            try:
                config = json.loads(client_path.read_text(encoding="utf-8-sig"))["web"]
                client_id, client_secret = config["client_id"], config["client_secret"]
            except (ValueError, KeyError, TypeError):
                raise ValueError("credentials.web.json에는 웹 애플리케이션 유형의 OAuth JSON을 저장하세요.") from None
        if bool(client_id) != bool(client_secret):
            raise ValueError("웹 Google Client ID와 Secret을 모두 설정하세요.")
        return cls(base, directory, key, client_id,
                   client_secret, os.environ.get("BAZE_BASE_URL", "").strip(),
                   os.environ.get("BAZE_API_KEY", "").strip(), os.environ.get("WEB_AI_ENABLED", "false").lower() == "true",
                   0, 0, database_url, 2000,
                   (os.environ.get('SCHOOL_EMAIL_DOMAIN', '').strip().lower()
                    or ('js.hs.kr' if os.environ.get('RENDER_EXTERNAL_URL') else '')))
