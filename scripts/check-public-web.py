"""Read-only deployment checks. Does not log in, sync, or generate AI output."""

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description="공개 배포의 비로그인 접근 검사 (읽기 전용)")
    parser.add_argument("origin", help="예: https://실제서비스.onrender.com")
    args = parser.parse_args()
    origin = args.origin.rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        parser.error("경로·인증정보가 없는 HTTPS 원점을 입력하세요.")
    opener = build_opener(NoRedirect())
    checks = []

    def get(path, method="GET"):
        try:
            response = opener.open(Request(origin + path, method=method, headers={"User-Agent": "Moa-Deployment-Check/1"}), timeout=20)
        except HTTPError as error:
            response = error
        except (URLError, OSError):
            raise SystemExit(f"접속 실패: {path}. 응답 내용·인증정보는 출력하지 않습니다.") from None
        with response:
            return response.status, response.headers, response.read(200000).decode("utf-8", errors="replace")

    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})

    status, headers, body = get("/")
    check("public_home", status == 200 and 'href="/auth/google"' in body and 'id="app-data"' not in body)
    check("homepage_brand_and_purpose", '<h1>모아</h1>' in body and 'Google Classroom의 과제' in body)
    check("homepage_privacy_link", 'href="'+origin+'/privacy"' in body)
    check("homepage_head_accessible", get('/', method='HEAD')[0] == 200)
    check("private_cache_policy", "no-store" in headers.get("Cache-Control", ""))
    check("frame_protection", headers.get("X-Frame-Options") == "DENY")
    status, _, body = get("/health")
    try:
        health = json.loads(body)
    except ValueError:
        health = {}
    check("health_and_oauth_configured", status == 200 and health.get("status") == "ok" and health.get("google_login_configured") is True)
    status, _, body = get("/privacy")
    check("privacy_page", status == 200)
    check("privacy_disclosures", all(value in body for value in ('모아 개인정보처리방침','Render','Neon','BAZE','보관 기간과 삭제','Google API Services User Data Policy')))
    check("privacy_head_accessible", get('/privacy', method='HEAD')[0] == 200)
    status, _, body = get('/robots.txt')
    check("public_information_crawlable_while_awake", status == 200 and 'Allow: /privacy' in body)
    for path in ("/api/data", "/api/courses", "/api/session", "/api/jobs/latest"):
        status, _, _ = get(path)
        check("anonymous_blocked:" + path, status == 401)
    for path in ("/.env", "/credentials.web.json", "/.local/web/web.sqlite3"):
        status, _, _ = get(path)
        check("private_file_blocked:" + path, status in (403, 404))
    status, headers, _ = get("/auth/google")
    target = urlsplit(headers.get("Location", ""))
    query = parse_qs(target.query)
    check("google_redirect_and_pkce", status in (302, 303, 307) and target.scheme == "https" and target.hostname == "accounts.google.com"
          and query.get("redirect_uri") == [origin + "/auth/callback"] and query.get("code_challenge_method") == ["S256"]
          and bool(query.get("state")) and bool(query.get("nonce")))
    print(json.dumps({"origin": origin, "checks": checks, "real_login_verified": False}, ensure_ascii=False, indent=2))
    return 0 if all(item["passed"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
