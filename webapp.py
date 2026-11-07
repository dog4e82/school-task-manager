"""Multi-account Classroom web service. Run with uv run webapp.py serve."""

import argparse
import hmac
import json
import logging
import os
import secrets
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime
from urllib.parse import urlsplit

import httplib2
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pydantic import BaseModel, Field, ConfigDict
from oauthlib.oauth2 import InvalidClientError, InvalidGrantError

from classroom import READ_SCOPES, SYNC_SCOPES, list_courses
from classroom_data import collect_snapshot, SEOUL
from classroom_pdf import enrich_snapshot, references
from main import Client
from notice_ai import Cache, DEFAULT_MODEL, prepare, run_analysis, post_key
from task_priority import prioritize_posts
from ui import render_html
from ui_data import build_data, SavedAnalyses
from web_pages import landing, setup, privacy
from web_settings import Settings, ROOT, google_config_fingerprints
from web_store import Store, digest


WEB_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]
LOGGER = logging.getLogger("moa")


class MissingLoginScopes(ValueError):
    """The token response did not grant the permissions needed by this login."""


def accept_granted_scopes(flow, requested):
    """Accept a genuine grant superset without disabling OAuth scope validation."""
    required = set(requested)

    def check(response):
        if response.status_code != 200:
            return response  # Let the OAuth parser classify token endpoint errors.
        payload = response.json()
        if payload.get("error"):
            return response
        scopes = payload.get("scope")
        if not isinstance(scopes, str) or not required.issubset(scopes.split()):
            raise MissingLoginScopes()
        # Google may also return permissions previously granted to this project.
        # Keep the real grant in credentials; never invent or widen a grant.
        flow.oauth2session.scope = scopes.split()
        return response

    flow.oauth2session.register_compliance_hook("access_token_response", check)


class SyncBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_ids: list[str] = Field(min_length=1, max_length=50)
    include_pdf: bool = False


class AnalyzeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: bool
    limit: int = Field(default=3, ge=1, le=3)


class PersonalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, max_length=240)
    completed: bool | None = None
    saved: bool | None = None
    note: str | None = Field(default=None, max_length=3000)
    deadline: str | None = None


def create_app(settings=None):
    settings = settings or Settings.load()
    store = Store(settings.data_dir, settings.token_key, settings.database_url)
    if settings.configured:
        try:
            store.record_oauth_config(google_config_fingerprints(settings.client_id, settings.client_secret, settings.token_key))
        except Exception:
            LOGGER.warning('oauth_config_diagnostics_unavailable')
    cache_path = settings.data_dir / "analysis.sqlite3"
    def analysis_cache(readonly=False):
        if settings.database_url:
            from postgres_storage import PostgresCache
            return PostgresCache(settings.database_url, readonly=readonly)
        return SavedAnalyses(cache_path) if readonly else Cache(cache_path)
    analysis_cache().close()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="moa-job")

    def login_event(stage, result):
        try:
            store.record_login(stage, result)
        except Exception:
            # Diagnostics must never change whether a login succeeds or fails.
            LOGGER.warning('oauth_diagnostics_unavailable')

    @asynccontextmanager
    async def lifespan(app):
        store.recover_jobs()
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.settings, app.state.executor = store, settings, executor
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list({urlsplit(settings.base_url).hostname, "localhost", "127.0.0.1"}))

    @app.middleware("http")
    async def response_policy(request, call_next):
        if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > 32768:
            response = JSONResponse({"detail": "요청 크기가 너무 큽니다."}, status_code=413)
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                LOGGER.warning("web_request_failed:%s", type(exc).__name__)
                response = JSONResponse({"detail": "요청을 처리하지 못했습니다. 연결 상태를 확인해 주세요."}, status_code=500)
        response.headers.update({"Cache-Control": "no-store, private", "Pragma": "no-cache",
                                 "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path in ("/", "/setup", "/privacy"):
            response.headers["Content-Security-Policy"] += "; default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'"
        return response

    def session(request):
        value = store.session(request.cookies.get(settings.cookie, ""))
        if not value:
            raise HTTPException(401, "Google 계정으로 로그인해 주세요.")
        return value

    def mutation(request):
        value = session(request)
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied, value["csrf"]) or request.headers.get("origin", settings.base_url) != settings.base_url:
            raise HTTPException(403, "이 화면에서 시작한 요청인지 확인하지 못했습니다. 새로고침해 주세요.")
        return value

    def get_credentials(user_id):
        user = store.get_user(user_id)
        if not user:
            raise ValueError("user_missing")
        creds = Credentials.from_authorized_user_info(user["credentials"])
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            store.update_credentials(user_id, json.loads(creds.to_json()))
        if not creds.valid or not creds.has_scopes(READ_SCOPES):
            raise ValueError("reauth_required")
        return creds

    def google_service(name, creds):
        return build(name, "v3" if name == "drive" else "v1", http=AuthorizedHttp(creds, http=httplib2.Http(timeout=30)), cache_discovery=False)

    def own_courses(user_id):
        creds = get_credentials(user_id)
        service = google_service("classroom", creds)
        try:
            return list_courses(service)
        finally:
            service.close()
            store.update_credentials(user_id, json.loads(creds.to_json()))

    def data_for(user_id):
        snapshot = store.snapshot(user_id)
        if snapshot is None:
            raise HTTPException(409, "먼저 모아 볼 수업을 선택해 주세요.")
        cache = analysis_cache(readonly=True)
        try:
            return build_data(snapshot, cache, settings.baze_base)
        finally:
            cache.close()

    def run_sync(user_id, job_id, selected, include_pdf):
        creds = None
        try:
            store.finish_job(user_id, job_id, "running", "계정의 수업 접근 권한 확인 중")
            creds = get_credentials(user_id)
            service = google_service("classroom", creds)
            try:
                available = {c["id"]: c for c in list_courses(service)}
                if any(c not in available for c in selected):
                    raise ValueError("course_not_accessible")
                store.finish_job(user_id, job_id, "running", "선택한 수업의 과제·공지·자료 수집 중")
                snapshot = collect_snapshot(service, [available[c] for c in selected], include_materials=True)
            finally:
                service.close()
            for post in snapshot["assignments"] + snapshot["announcements"] + snapshot["materials"]:
                post["attachments"] = references(post)
            store.save_snapshot(user_id, snapshot)
            if include_pdf:
                if not creds.has_scopes(SYNC_SCOPES):
                    raise ValueError("drive_scope_missing")
                store.finish_job(user_id, job_id, "running", "본문 저장 완료 · 현재 안내의 PDF 확인 중")
                drive = google_service("drive", creds)
                try:
                    posts = snapshot["assignments"] + snapshot["announcements"] + snapshot["materials"]
                    keys = {post_key(p) for p in prioritize_posts(posts)[:10]}
                    enrich_snapshot(snapshot, drive, settings.data_dir / "users" / user_id / "pdf-cache",
                                    checkpoint=lambda value: store.save_snapshot(user_id, value), post_keys=keys)
                finally:
                    drive.close()
            store.save_snapshot(user_id, snapshot)
            store.finish_job(user_id, job_id, "done", "수업 연결 완료", {"courses": len(selected), "partial": not snapshot["complete"]})
        except Exception as exc:
            LOGGER.warning("sync_job_failed:%s", type(exc).__name__)
            store.finish_job(user_id, job_id, "failed", "수집을 완료하지 못했어요. Google 읽기 권한과 학교의 앱 허용 여부를 확인하세요.")
        finally:
            if creds:
                store.update_credentials(user_id, json.loads(creds.to_json()))

    def run_ai(user_id, job_id, limit):
        cache = None
        try:
            snapshot = store.snapshot(user_id)
            if not snapshot:
                raise ValueError("snapshot_missing")
            store.finish_job(user_id, job_id, "running", "현재 안내를 AI로 정리 중 · 저장된 결과는 재사용합니다")
            jobs = prepare(snapshot, DEFAULT_MODEL, settings.baze_base)
            cache = analysis_cache()
            report = run_analysis(Client(settings.baze_base, settings.baze_key), cache, jobs, DEFAULT_MODEL, limit=limit)
            store.finish_job(user_id, job_id, "done" if not report["failed"] else "failed",
                             "정리 완료" if not report["failed"] else "일부 결과를 확인하지 못했어요. 저장된 결과부터 확인하세요.", report)
        except Exception as exc:
            LOGGER.warning("analysis_job_failed:%s", type(exc).__name__)
            store.finish_job(user_id, job_id, "failed", "AI 연결을 완료하지 못했어요. 자동으로 다시 호출하지 않았습니다.")
        finally:
            if cache:
                cache.close()

    def enqueue(user_id, kind, body):
        try:
            job_id = store.new_job(user_id, kind, datetime.now(SEOUL).date().isoformat(),
                                   body.limit if kind == "analyze" else 0, settings.ai_daily_limit, settings.ai_global_daily_limit)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 진행 중인 작업이 있습니다.") from None
        except ValueError as exc:
            if str(exc) == "server_busy":
                raise HTTPException(503, "현재 연결 작업이 많아요. 잠시 후 다시 시도해 주세요.") from None
            raise HTTPException(429, "오늘 실행할 수 있는 AI 정리 횟수에 도달했습니다.") from None
        if kind == "sync":
            executor.submit(run_sync, user_id, job_id, list(dict.fromkeys(body.course_ids)), body.include_pdf)
        else:
            executor.submit(run_ai, user_id, job_id, body.limit)
        return {"job_id": job_id}

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def home(request: Request, error: str | None = None):
        # The informational homepage is public even with a session cookie and
        # remains independent of database availability. /app is the dashboard.
        return HTMLResponse(landing(settings.configured, error, settings.base_url))

    @app.get("/health")
    def health():
        return {"status": "ok", "google_login_configured": settings.configured,
                "oauth_flow_version": 4, "public_pages_version": 1}

    @app.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def privacy_page():
        return HTMLResponse(privacy())

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        return PlainTextResponse("User-agent: *\nAllow: /$\nAllow: /privacy\nDisallow: /auth/\nDisallow: /api/\nDisallow: /app\nDisallow: /setup\n")

    @app.get("/assets/{name}")
    def asset(name: str):
        allowed = {"account.css": "text/css", "account.js": "text/javascript"}
        if name not in allowed:
            raise HTTPException(404)
        return FileResponse(ROOT / "web" / name, media_type=allowed[name])

    @app.get("/auth/google")
    def login(pdf: bool = False):
        if not settings.configured:
            return RedirectResponse("/?error=oauth_failed", status_code=303)
        verifier, nonce = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        scopes = WEB_SCOPES + (SYNC_SCOPES if pdf else READ_SCOPES)
        state, binding = store.begin_oauth({"verifier": verifier, "nonce": nonce, "scopes": scopes})
        login_event('start', 'started')
        flow = Flow.from_client_config(settings.google_config(), scopes=scopes, state=state, code_verifier=verifier)
        flow.redirect_uri = settings.callback
        url, _ = flow.authorization_url(access_type="offline", prompt="select_account consent", nonce=nonce)
        response = RedirectResponse(url, status_code=303)
        response.set_cookie("moa_oauth", binding, max_age=600, httponly=True, secure=settings.secure, samesite="lax", path="/auth")
        return response

    @app.get("/auth/callback")
    def callback(request: Request, state: str = "", code: str = "", error: str = ""):
        login_event('callback', 'received')
        pending = store.consume_oauth(state, request.cookies.get("moa_oauth", "")) if state else None
        if not pending:
            login_event('callback', 'state_expired')
            response = RedirectResponse("/?error=state_expired", status_code=303)
        elif error or not code:
            login_event('callback', 'denied')
            response = RedirectResponse("/?error=google_denied", status_code=303)
        else:
            stage = "token"
            try:
                flow = Flow.from_client_config(settings.google_config(), scopes=pending["scopes"], state=state, code_verifier=pending["verifier"])
                flow.redirect_uri = settings.callback
                accept_granted_scopes(flow, pending["scopes"])
                flow.fetch_token(code=code, timeout=30)
                stage = "identity"
                claims = id_token.verify_oauth2_token(flow.oauth2session.token["id_token"], GoogleRequest(), settings.client_id)
                if (not hmac.compare_digest(str(claims.get("nonce", "")), pending["nonce"])
                        or not claims.get("sub") or claims.get("email_verified") is not True):
                    raise ValueError("invalid_identity")
                stage = "permissions"
                credentials = flow.credentials
                if not credentials.valid or not credentials.has_scopes(READ_SCOPES):
                    raise MissingLoginScopes()
                serialized = json.loads(credentials.to_json())
                stage = "storage"
                prior = store.get_user(digest("google:" + claims["sub"]))
                if not serialized.get("refresh_token") and prior:
                    serialized["refresh_token"] = prior["credentials"].get("refresh_token")
                user_id = store.save_user(claims["sub"], claims.get("email", ""), claims.get("name") or "학생", serialized)
                stage = "session"
                store.delete_session(request.cookies.get(settings.cookie, ""))
                token = store.create_session(user_id)
                response = RedirectResponse("/setup", status_code=303)
                response.set_cookie(settings.cookie, token, max_age=604800, httponly=True, secure=settings.secure, samesite="lax", path="/")
                login_event('session', 'success')
            except Exception as exc:
                if isinstance(exc, MissingLoginScopes):
                    stage = "permissions"
                reason = ('missing_scopes' if isinstance(exc, MissingLoginScopes)
                          else 'invalid_client' if isinstance(exc, InvalidClientError)
                          else 'invalid_grant' if isinstance(exc, InvalidGrantError)
                          else 'scope_changed' if isinstance(exc, Warning)
                          else 'network' if isinstance(exc, requests.RequestException)
                          else 'failed')
                login_event(stage, reason)
                # Exception messages can contain tokens or callback URLs. Log only
                # our fixed stage and the exception class, never the exception.
                LOGGER.warning("oauth_callback_failed:%s:%s", stage, type(exc).__name__)
                response = RedirectResponse("/?error=oauth_" + stage + "_failed", status_code=303)
        response.delete_cookie("moa_oauth", path="/auth", secure=settings.secure, httponly=True, samesite="lax")
        return response

    @app.get("/setup", response_class=HTMLResponse)
    def select_courses(request: Request):
        try:
            current = session(request)
        except HTTPException:
            return RedirectResponse("/", status_code=303)
        user = store.get_user(current["user_id"])
        prior = store.snapshot(user["id"])
        creds = Credentials.from_authorized_user_info(user["credentials"])
        return HTMLResponse(setup(user, current["csrf"], [c["id"] for c in prior["courses"]] if prior else [], creds.has_scopes(SYNC_SCOPES), settings.ai_enabled))

    @app.get("/app", response_class=HTMLResponse)
    def dashboard(request: Request):
        try:
            current = session(request)
        except HTTPException:
            return RedirectResponse("/", status_code=303)
        if store.snapshot(current["user_id"]) is None:
            return RedirectResponse("/setup", status_code=303)
        data = data_for(current["user_id"])
        user = store.get_user(current["user_id"])
        data["web"] = {"userId": user["id"], "name": user["name"], "csrf": current["csrf"],
                       "hasDrive": Credentials.from_authorized_user_info(user["credentials"]).has_scopes(SYNC_SCOPES),
                       "personal": store.personal(user["id"]), "aiEnabled": settings.ai_enabled and bool(settings.baze_base and settings.baze_key)}
        return HTMLResponse(render_html(data))

    @app.get("/api/courses")
    def courses(request: Request):
        current = session(request)
        try:
            return {"courses": [{"id": c["id"], "name": c.get("name", "이름 없는 수업"), "state": c.get("courseState")} for c in own_courses(current["user_id"])]}
        except Exception:
            raise HTTPException(403, "수업을 읽지 못했어요. Google 읽기 권한과 학교의 앱 허용 여부를 확인하세요.") from None

    @app.get("/api/data")
    def api_data(request: Request):
        return data_for(session(request)["user_id"])

    @app.get("/api/session")
    def current_session(request: Request):
        return {"user_id": session(request)["user_id"]}

    @app.post("/api/sync", status_code=202)
    def sync(request: Request, body: SyncBody):
        current = mutation(request)
        if any(not value or len(value) > 100 for value in body.course_ids):
            raise HTTPException(422, "수업 선택이 올바르지 않습니다.")
        if body.include_pdf and not get_credentials(current["user_id"]).has_scopes(SYNC_SCOPES):
            raise HTTPException(403, "첨부 PDF 읽기 권한을 먼저 연결해 주세요.")
        return enqueue(current["user_id"], "sync", body)

    @app.post("/api/analyze", status_code=202)
    def analyze(request: Request, body: AnalyzeBody):
        current = mutation(request)
        if not settings.ai_enabled or not settings.baze_base or not settings.baze_key:
            raise HTTPException(503, "공지 AI 정리는 운영자가 연결을 준비하고 있습니다.")
        if not body.consent:
            raise HTTPException(400, "선택한 공지를 BAZE로 전송하는 데 동의해야 합니다.")
        data_for(current["user_id"])
        return enqueue(current["user_id"], "analyze", body)

    @app.get("/api/jobs/latest")
    def latest(request: Request):
        return {"job": store.latest_job(session(request)["user_id"])}

    @app.get("/api/jobs/{job_id}")
    def job_status(request: Request, job_id: str):
        value = store.job(session(request)["user_id"], job_id)
        if value is None:
            raise HTTPException(404)
        return value

    @app.post("/api/personal")
    def personal(request: Request, body: PersonalBody):
        current = mutation(request)
        data = data_for(current["user_id"])
        allowed = {t["id"] for t in data["tasks"] + data["schedule"]} | {"opportunity:" + o["postId"] for o in data["opportunities"]}
        if body.item_id not in allowed:
            raise HTTPException(404, "현재 계정에 연결된 항목이 아닙니다.")
        patch = body.model_dump(exclude_unset=True, exclude={"item_id"})
        if "deadline" in patch and patch["deadline"]:
            try:
                if date.fromisoformat(patch["deadline"]).isoformat() != patch["deadline"]:
                    raise ValueError()
            except ValueError:
                raise HTTPException(422, "날짜 형식이 올바르지 않습니다.") from None
        store.save_personal(current["user_id"], body.item_id, patch)
        return {"saved": True}

    @app.post("/api/logout")
    def logout(request: Request):
        mutation(request)
        store.delete_session(request.cookies.get(settings.cookie, ""))
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(settings.cookie, path="/", secure=settings.secure, httponly=True, samesite="lax")
        return response

    @app.delete("/api/account")
    def delete_account(request: Request):
        current = mutation(request)
        latest = store.latest_job(current["user_id"])
        if latest and latest["status"] in ("queued", "running"):
            raise HTTPException(409, "진행 중인 작업이 끝난 뒤 연결을 해제해 주세요.")
        user = store.get_user(current["user_id"])
        token = user["credentials"].get("refresh_token") or user["credentials"].get("token")
        if token:
            try:
                response = requests.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=20)
                if response.status_code not in (200, 400):
                    raise ValueError()
            except Exception:
                raise HTTPException(502, "Google 연결 취소를 확인하지 못했어요. 잠시 후 다시 시도해 주세요.") from None
        directory = settings.data_dir / "users" / current["user_id"]
        if directory.exists():
            if directory.is_symlink() or not directory.resolve().is_relative_to((settings.data_dir / "users").resolve()):
                raise HTTPException(500, "계정 파일 경로를 확인하지 못했습니다.")
            shutil.rmtree(directory)
        store.delete_user(current["user_id"])
        response = JSONResponse({"deleted": True})
        response.delete_cookie(settings.cookie, path="/", secure=settings.secure, httponly=True, samesite="lax")
        return response

    return app


def main():
    parser = argparse.ArgumentParser(description="모아 다중 사용자 웹 서버")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    commands.add_parser("check", help="비밀값 출력 없이 웹 설정 확인")
    commands.add_parser("seed-cache", help="기존 성공 분석만 웹 공통 캐시에 복사. OAuth·수집본·개인 기록은 복사하지 않음")
    args = parser.parse_args()
    try:
        settings = Settings.load()
        if args.command == "check":
            print("웹 Google OAuth: " + ("설정됨" if settings.configured else "웹 앱용 ID·Secret 설정 필요"))
            print("리디렉션 URI: " + settings.callback)
            print("토큰 암호화: 설정됨 / AI 모델: " + DEFAULT_MODEL)
            print("공개 배포 여부는 이 명령에서 확인하지 않습니다.")
        elif args.command == "seed-cache":
            source = ROOT / ".local" / "classroom" / "analysis.sqlite3"
            if not source.exists():
                raise ValueError("기존 분석 캐시가 없습니다.")
            if settings.database_url:
                from postgres_storage import PostgresCache
                target = PostgresCache(settings.database_url)
            else:
                target = Cache(settings.data_dir / "analysis.sqlite3")
            with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as legacy:
                rows = legacy.execute("SELECT key,post_key,model,status,result,NULL,updated_at FROM analyses WHERE status='success' AND model=?", (DEFAULT_MODEL,)).fetchall()
            legacy.close()
            before = target.conn.total_changes
            with target.conn:
                target.conn.executemany("INSERT OR IGNORE INTO analyses VALUES (?,?,?,?,?,?,?)", rows)
            print(f"성공 분석 {target.conn.total_changes-before}건 복사. 계정 인증정보와 수집본 복사 없음.")
            target.close()
        else:
            import uvicorn
            uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False, proxy_headers=False)
        return 0
    except ValueError as exc:
        print(f"설정 오류: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
