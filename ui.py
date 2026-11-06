"""Generate an interactive offline UI from existing data, with no API calls."""

import argparse
import base64
import hashlib
import json
import os
import webbrowser
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from ui_data import load_data


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / ".local" / "classroom-ui.html"


def render_html(data, root=None):
    root = root or ROOT
    template = (root / "web" / "index.html").read_text(encoding="utf-8")
    style = (root / "web" / "app.css").read_text(encoding="utf-8")
    script = (root / "web" / "app.js").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    parts = {"{{STYLE}}": style, "{{DATA}}": payload, "{{SCRIPT}}": script, "{{SCRIPT_HASH}}": script_hash,
             "{{CONNECT_SRC}}": "'self'" if data.get("web") else "'none'"}
    import re
    return re.sub(r"\{\{(?:STYLE|DATA|SCRIPT|SCRIPT_HASH|CONNECT_SRC)\}\}", lambda match: parts[match.group()], template)


def export(today=None, open_browser=False):
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    snapshot = ROOT / ".local" / "classroom" / "snapshot.json"
    if not snapshot.exists():
        raise SystemExit("저장된 수집본이 없습니다. 현재 UI는 저장된 데이터만 사용합니다.")
    provider = os.environ.get("BAZE_BASE_URL", "").strip()
    if not provider:
        raise SystemExit("기존 BAZE_BASE_URL 설정이 필요합니다. API를 호출하지 않고 캐시를 찾는 데만 사용합니다.")
    data = load_data(snapshot, snapshot.with_name("analysis.sqlite3"), provider, today)
    output = render_html(data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(output, encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"UI: {OUTPUT}")
    print(f"연결: 수업 {len(data['courses'])}개 / 게시물 {len(data['posts'])}개 / 현재 모델 분석 {data['stats']['analyzed']}개")
    print("추가 API 호출 없음. 완료 표시와 개인 메모는 이 브라우저에 저장됩니다.")
    if open_browser:
        webbrowser.open(OUTPUT.as_uri())
    return OUTPUT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="저장 데이터로 과제 UI 생성 (API 호출 없음)")
    parser.add_argument("--open", action="store_true", help="생성한 화면을 브라우저에서 열기")
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    export(args.as_of, args.open)
