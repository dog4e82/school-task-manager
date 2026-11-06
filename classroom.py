"""Local Google Classroom OAuth connection and course selection."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException
from dotenv import load_dotenv

from classroom_data import CollectionError, collect_snapshot, show_tasks
from classroom_errors import error_reason, operation
from classroom_pdf import enrich_snapshot
from main import BazeError, Client
from notice_ai import AnalysisError, Cache, DEFAULT_MODEL, prepare, run_analysis, show_results
from task_priority import prioritize_posts


ROOT = Path(__file__).resolve().parent
CLIENT_FILE = ROOT / "credentials.json"
STATE_DIR = ROOT / ".local" / "classroom"
TOKEN_FILE = STATE_DIR / "token.json"
SELECTION_FILE = STATE_DIR / "selected_courses.json"
SCOPES = ["https://www.googleapis.com/auth/classroom.courses.readonly"]
READ_SCOPES = SCOPES + [
    # Google returns this name for coursework.me.readonly on consent.
    # Request it directly; retain oauthlib's strict scope comparison.
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
]
SYNC_SCOPES = READ_SCOPES + ["https://www.googleapis.com/auth/drive.readonly"]
SNAPSHOT_FILE = STATE_DIR / "snapshot.json"


class ClassroomError(Exception):
    pass


def save_json(path, value):
    """Replace complete local state; never leave a partially written token."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def credentials(reauth=False, scopes=None, upgrade=False):
    scopes = scopes or SCOPES
    creds = None
    if TOKEN_FILE.exists() and not reauth:
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        except (ValueError, TypeError, KeyError):
            raise ClassroomError("저장된 로그인 정보가 올바르지 않습니다. connect --reauth로 다시 로그인하세요.") from None
        if not creds.has_scopes(scopes):
            if upgrade:
                print("과제·공지·자료와 첨부 PDF에 필요한 읽기 권한을 추가로 요청합니다.")
                creds = None
            else:
                raise ClassroomError("클래스룸 조회 권한이 없습니다. connect --reauth로 다시 동의하세요.")
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except GoogleAuthError:
            raise ClassroomError("로그인 갱신 실패. connect --reauth로 다시 로그인하세요.") from None
    if not creds or not creds.valid:
        if not CLIENT_FILE.exists():
            raise ClassroomError(
                "credentials.json이 없습니다. Google Cloud에서 데스크톱 앱 OAuth JSON을 "
                "다운로드하고 프로젝트 폴더에 credentials.json으로 저장하세요. README의 Classroom 설정을 참고하세요."
            )
        config = json.loads(CLIENT_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or not isinstance(config.get("installed"), dict):
            raise ClassroomError("데스크톱 앱 유형의 OAuth JSON이 필요합니다. Google Cloud의 Clients에서 확인하세요.")
        flow = InstalledAppFlow.from_client_config(config, scopes, autogenerate_code_verifier=True)
        print("브라우저에서 학교 계정을 선택하고 요청한 읽기 권한을 허용하세요. (최대 3분 대기)")
        try:
            creds = flow.run_local_server(
                host="127.0.0.1", port=0, open_browser=True, timeout_seconds=180,
                authorization_prompt_message="로그인 창을 열었습니다. 브라우저에서 완료하세요.",
                success_message="로그인되었습니다. 이 창을 닫고 터미널로 돌아가세요.",
                prompt="select_account consent",
            )
        except Warning:
            # oauthlib raises Warning on scope mismatch. Its token attribute may
            # contain credentials, so do not print this exception or its details.
            raise ClassroomError(
                "Google이 요청과 다른 권한을 반환했습니다. 로그인 정보를 변경하지 않았습니다. "
                "uv run classroom.py sync --reauth로 다시 로그인하고 요청한 읽기 권한을 모두 허용하세요."
            ) from None
        granted = creds.granted_scopes if creds else None
        if (not creds or not creds.valid or not creds.has_scopes(scopes)
                or (granted is not None and not set(scopes).issubset(granted))):
            raise ClassroomError("로그인 또는 읽기 권한 동의가 완료되지 않았습니다.")
        # A new login can select a different account. Discard its predecessor's selection.
        SELECTION_FILE.unlink(missing_ok=True)
        SNAPSHOT_FILE.unlink(missing_ok=True)
    save_json(TOKEN_FILE, json.loads(creds.to_json()))
    return creds


def list_courses(service):
    """Follow every nextPageToken, including empty intermediate pages."""
    courses, seen = [], set()
    token = None
    while True:
        params = {"pageSize": 100}
        if token:
            params["pageToken"] = token
        page = service.courses().list(**params).execute(num_retries=0)
        entries = page.get("courses", [])
        if not isinstance(entries, list) or not all(
            isinstance(c, dict) and isinstance(c.get("id"), str) for c in entries
        ):
            raise ClassroomError("클래스룸 목록 응답 형식이 예상과 다릅니다.")
        courses.extend(entries)
        token = page.get("nextPageToken")
        if not token:
            return courses
        if not isinstance(token, str) or token in seen:
            raise ClassroomError("다음 페이지 정보가 올바르지 않습니다. 목록을 다시 조회하세요.")
        seen.add(token)


def parse_selection(text, count):
    if text.strip().lower() == "all":
        return list(range(count))
    try:
        numbers = sorted({int(part.strip()) - 1 for part in text.split(",")})
    except ValueError:
        raise ClassroomError("번호를 쉼표로 구분하세요. 예: 1,3 또는 all") from None
    if not numbers or any(n < 0 or n >= count for n in numbers):
        raise ClassroomError("목록에 표시된 번호만 입력하세요.")
    return numbers


def choose_courses(courses):
    while True:
        text = input("통합할 수업 번호 (예: 1,3 / 전체: all / 취소: Enter): ")
        if not text.strip():
            print("선택을 취소했습니다.")
            return
        try:
            indexes = parse_selection(text, len(courses))
        except ClassroomError as exc:
            print(exc)
            continue
        selected = [{k: courses[i][k] for k in ("id", "name", "alternateLink") if k in courses[i]}
                    for i in indexes]
        save_json(SELECTION_FILE, {"courses": selected})
        print(f"{len(selected)}개 수업 선택을 로컬에 저장했습니다.")
        return


def sync(service, courses, drive=None, pdf_limit=None):
    if not SELECTION_FILE.exists():
        print("계정에 맞는 수업을 선택하세요.")
        choose_courses(courses)
        if not SELECTION_FILE.exists():
            raise ClassroomError("수업 선택이 없어 수집하지 않았습니다.")
    selected = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))["courses"]
    if not selected or not all(isinstance(c, dict) and isinstance(c.get("id"), str) for c in selected):
        raise ClassroomError("수업 선택 정보가 올바르지 않습니다. connect 명령으로 다시 선택하세요.")
    by_id = {c["id"]: c for c in courses}
    if any(c["id"] not in by_id for c in selected):
        raise ClassroomError("선택한 수업 중 현재 접근할 수 없는 수업이 있습니다. connect로 다시 선택하세요.")
    snapshot = collect_snapshot(service, [by_id[c["id"]] for c in selected], include_materials=True)
    if drive is not None:
        snapshot.update(pdf_processing=True, pdf_collection_complete=False)
        save_json(SNAPSHOT_FILE, snapshot)
        selected_keys = None
        if pdf_limit is not None:
            posts = prioritize_posts(snapshot["assignments"] + snapshot["announcements"] + snapshot["materials"])
            selected_keys = {f"{p['course_id']}:{p['source']}:{p['id']}" for p in posts[:pdf_limit]}
            print(f"현재 과제·최근 안내를 우선해 게시물 {len(selected_keys)}개의 첨부를 확인합니다.")
        counts = enrich_snapshot(snapshot, drive, STATE_DIR / "pdf-cache",
                                 checkpoint=lambda value: save_json(SNAPSHOT_FILE, value), post_keys=selected_keys)
        print("첨부 확인 결과: " + json.dumps(counts, ensure_ascii=False))
        if counts.get("drive_api_disabled"):
            print("Google Cloud에서 Google Drive API를 사용 설정한 뒤 sync를 다시 실행하세요.")
    save_json(SNAPSHOT_FILE, snapshot)
    complete = snapshot["complete"] and snapshot.get("pdf_collection_complete", True)
    status = "수집 완료" if complete else "부분 수집 완료"
    print(f"{status}: 수업 {len(selected)}개 / 과제·질문 {len(snapshot['assignments'])}개 / 공지 {len(snapshot['announcements'])}개 / 자료 {len(snapshot['materials'])}개")
    show_tasks(snapshot)
    return complete


def ai_command(args):
    if not SNAPSHOT_FILE.exists():
        raise ClassroomError("uv run classroom.py sync로 게시물을 먼저 수집하세요.")
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    base = os.environ.get("BAZE_BASE_URL", "").strip()
    key = os.environ.get("BAZE_API_KEY", "").strip()
    if not base:
        raise ClassroomError(".env의 BAZE_BASE_URL을 설정하세요.")
    snapshot = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    jobs = prepare(snapshot, args.model, base, with_context=args.with_context)
    if getattr(args, "focus", "all") == "opportunities":
        from opportunities import candidate
        jobs = [job for job in jobs if candidate(job["post"])]
        jobs.sort(key=lambda job: job["post"].get("raw", {}).get("creationTime", ""), reverse=True)
        print("대회·공모·선택 활동 안내 후보를 최신순으로 확인합니다. 키워드만으로 선택 활동을 확정하지 않습니다.")
    if getattr(args, "title", None):
        jobs = [job for job in jobs if args.title.casefold() in job["post"].get("title", "").casefold()]
        if not jobs:
            raise ClassroomError("해당 제목의 게시물이 없습니다. sync로 자료 게시물까지 다시 수집하세요.")
    if not snapshot.get("materials_collected"):
        print("이 수집본에는 자료 게시물이 빠져 있습니다. sync로 다시 수집하면 자료와 PDF도 포함됩니다.")
    if not snapshot.get("complete", True):
        print("Classroom 수집에 미수집 항목이 있습니다. 조회에 성공한 게시물만 분석합니다.")
    cache = Cache(STATE_DIR / "analysis.sqlite3")
    try:
        if args.command == "ai-tasks":
            show_results(cache, jobs, limit=args.limit)
            return 0
        if not args.dry_run and not key:
            raise ClassroomError(".env의 BAZE_API_KEY를 설정하세요.")
        print(f"모델: {args.model} / 이번 실행 신규 생성 상한: {args.limit}회")
        print("분석 시 선택한 게시물의 제목·상세 본문과 추출한 첨부 PDF 텍스트가 BAZE로 전송됩니다.")
        if args.with_context:
            print("--with-context 선택: 같은 수업의 이전 게시물 최대 3개 발췌도 함께 전송됩니다.")
        client = None if args.dry_run else Client(base, key)
        report = run_analysis(client, cache, jobs, args.model, args.limit, args.retry_failed, args.dry_run)
        print("분석 진행: " + json.dumps(report, ensure_ascii=False))
        if not args.dry_run:
            show_results(cache, jobs)
        return 2 if report["failed"] else 0
    finally:
        cache.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Google Classroom 로그인·목록 조회·선택 (읽기 전용)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("connect", help="Google 로그인 후 통합할 수업 선택").add_argument(
        "--reauth", action="store_true", help="계정 변경 또는 재동의")
    commands.add_parser("courses", help="모든 페이지의 수업 목록 조회")
    sync_parser = commands.add_parser("sync", help="선택한 수업의 과제·공지 수집 후 마감순 표시")
    sync_parser.add_argument("--reauth", action="store_true", help="과제·공지 읽기 권한 재동의")
    sync_parser.add_argument("--pdf-limit", type=int, help="현재 과제·최신 안내 N개만 PDF를 우선 처리 (본문은 전체 수집)")
    commands.add_parser("tasks", help="저장한 과제 목록 보기 (네트워크 요청 없음)")
    analyze = commands.add_parser("analyze", help="수집한 게시물을 BAZE로 분석 (실제 과금 가능)")
    analyze.add_argument("--model", default=DEFAULT_MODEL)
    analyze.add_argument("--limit", type=int, default=3, help="이번 실행 신규 생성 상한 (기본 3)")
    analyze.add_argument("--dry-run", action="store_true", help="전송·생성 없이 처리 대상 건수만 확인")
    analyze.add_argument("--with-context", action="store_true", help="이전 게시물 발췌도 전송하여 후속 관계 분석 (기본은 현재 게시물만)")
    analyze.add_argument("--title", help="제목에 이 문자열이 있는 게시물만 분석")
    analyze.add_argument("--focus", choices=("all", "opportunities"), default="all",
                         help="opportunities: 대회·공모·신청·선택 활동 안내 후보를 최신순으로 분석")
    analyze.add_argument("--retry-failed", action="store_true", help="실패·불확실 호출을 명시적으로 재시도 (추가 과금 가능)")
    results = commands.add_parser("ai-tasks", help="저장한 AI 분석 결과 보기 (네트워크 요청 없음)")
    results.add_argument("--model", default=DEFAULT_MODEL)
    results.add_argument("--limit", type=int, default=20, help="표시 항목 수 (기본 20)")
    results.add_argument("--with-context", action="store_true", help="이전 게시물을 포함해 분석했던 결과 표시")
    results.add_argument("--title", help="제목에 이 문자열이 있는 결과만 표시")
    args = parser.parse_args(argv)
    if hasattr(args, "limit") and args.limit < 1:
        parser.error("--limit은 1 이상이어야 합니다.")
    if getattr(args, "pdf_limit", None) is not None and args.pdf_limit < 1:
        parser.error("--pdf-limit은 1 이상이어야 합니다.")
    exit_code = 0
    try:
        if args.command in ("analyze", "ai-tasks"):
            return ai_command(args)
        if args.command == "tasks":
            if not SNAPSHOT_FILE.exists():
                raise ClassroomError("수집한 과제가 없습니다. uv run classroom.py sync를 먼저 실행하세요.")
            show_tasks(json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8")))
            return 0
        if args.command == "sync":
            creds = credentials(reauth=args.reauth, scopes=SYNC_SCOPES, upgrade=True)
        else:
            creds = credentials(reauth=getattr(args, "reauth", False))
        service = build("classroom", "v1", credentials=creds, cache_discovery=False)
        try:
            courses = list_courses(service)
            print(f"Classroom API 연결 성공: 수업 {len(courses)}개 (모든 페이지 조회)")
            for number, course in enumerate(courses, 1):
                name = json.dumps(course.get("name", "이름 없음"), ensure_ascii=False)
                state = json.dumps(course.get("courseState", "UNKNOWN"))
                print(f"{number}. {name} [{state}]")
            if not courses:
                print("수업이 없습니다. Classroom을 사용하는 학교 계정으로 로그인했는지 확인하세요.")
            elif args.command == "connect":
                choose_courses(courses)
            elif args.command == "sync":
                drive = build("drive", "v3", credentials=creds, cache_discovery=False)
                try:
                    options = {"pdf_limit": args.pdf_limit} if args.pdf_limit is not None else {}
                    if sync(service, courses, drive=drive, **options) is False:
                        exit_code = 2
                finally:
                    drive.close()
        finally:
            service.close()
        return exit_code
    except (ClassroomError, CollectionError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except BazeError as exc:
        print(f"BAZE 오류: {exc}", file=sys.stderr)
    except (AnalysisError, sqlite3.Error):
        print("AI 응답 또는 로컬 분석 저장소 처리에 실패했습니다. 자동 재호출하지 않았습니다.", file=sys.stderr)
    except HttpError as exc:
        code = exc.resp.status
        reason = error_reason(exc)
        hint = {401: "connect --reauth로 다시 로그인하세요.",
                403: "Classroom API 활성화·학교 계정 권한·관리자의 외부 앱 허용 여부를 확인하세요.",
                429: "API 요청 한도에 도달했습니다. 잠시 후 다시 실행하세요."}.get(code, "API 조회 실패.")
        if reason == "ACCESS_TOKEN_SCOPE_INSUFFICIENT":
            hint = "필요한 읽기 권한이 없습니다. uv run classroom.py sync --reauth를 실행하세요."
        print(f"Classroom HTTP {code} [{operation(exc)} / {reason}]: {hint}", file=sys.stderr)
    except (GoogleAuthError, OAuth2Error):
        print("Google 인증 실패. 테스트 사용자에 학교 이메일을 추가했는지 확인하세요. "
              "관리자 차단이면 학교 관리자의 앱 허용이 필요합니다.", file=sys.stderr)
    except (OSError, RequestException):
        print("네트워크 연결 또는 로컬 파일 저장에 실패했습니다. 인터넷 연결과 파일 권한을 확인하세요.", file=sys.stderr)
    except (ValueError, TypeError, KeyError, AttributeError):
        if args.command in ("analyze", "ai-tasks"):
            print("AI 분석 입력 또는 저장된 결과 형식이 올바르지 않습니다. 자동 재호출하지 않았습니다.", file=sys.stderr)
        else:
            print("로그인이 시간 내 완료되지 않았거나 인증 파일·응답 형식이 올바르지 않습니다. "
                  "credentials.json을 확인한 뒤 다시 실행하세요.", file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("\n연결 또는 선택을 취소했습니다.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
