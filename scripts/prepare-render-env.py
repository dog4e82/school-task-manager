"""Prepare an ignored file for Render's environment import, without printing secrets."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web_settings import Settings


def main():
    settings = Settings.load()
    if not settings.database_url:
        raise ValueError(".env에 DATABASE_URL을 먼저 저장하세요. 연결 문자열은 채팅에 보내지 마세요.")
    if not settings.configured:
        raise ValueError("기존 credentials.web.json 또는 웹 Google OAuth 환경변수가 필요합니다.")
    values = {"DATABASE_URL": settings.database_url, "APP_TOKEN_KEY": settings.token_key,
              "GOOGLE_WEB_CLIENT_ID": settings.client_id, "GOOGLE_WEB_CLIENT_SECRET": settings.client_secret,
              "WEB_AI_ENABLED": "false"}
    # The provider URL also identifies saved analysis results when generation is off.
    if settings.baze_base:
        values["BAZE_BASE_URL"] = settings.baze_base
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("연결 값에 줄바꿈이 포함되어 있습니다. 설정 형식을 확인하세요.")
    output = ROOT / ".local" / "render.env"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text("".join(name+"="+json.dumps(value,ensure_ascii=False)+"\n" for name,value in values.items()),encoding="utf-8")
    print("Render 환경변수 가져오기 파일을 .local/render.env에 저장했습니다. 비밀값은 출력하지 않습니다.")
    print("이 파일은 Render 환경변수 설정에만 사용하고 Git·채팅에 올리지 마세요.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(str(error))
        raise SystemExit(1)
