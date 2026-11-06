# 모아 웹 버전 실행과 공개

웹 서버는 Python/FastAPI이고 패키지와 실행은 uv로 관리한다. 현재 구현은 브라우저 Google 로그인, 계정별 수업 선택, 전체 페이지 수집, 백그라운드 작업, 통합 기한, 계정별 개인 기록, 연결 해제를 지원한다. 모델은 `gpt-6.1-sol` 그대로다. 웹 서버가 기존 데스크톱 계정의 토큰이나 수집본을 다른 사용자에게 대신 연결하지 않는다.

## 1. 로컬에서 확인

```powershell
uv run webapp.py check
uv run webapp.py serve
```

브라우저에서 `http://127.0.0.1:8000`을 연다. 웹 OAuth가 없으면 연결 준비 안내가 나오며 실제 로그인은 시작하지 않는다. 기존 `uv run ui.py --open`은 API 호출 없는 개인 저장본 미리보기로 계속 사용할 수 있다.

Google Cloud의 같은 프로젝트에서 Google Auth platform → Clients → Create client → **Web application**을 만든다. 승인된 리디렉션 URI에 아래 주소를 정확하게 추가한다.

```text
http://127.0.0.1:8000/auth/callback
```

웹 클라이언트 JSON을 **`credentials.web.json`**으로 프로젝트 폴더에 저장한다. 이 파일은 Git와 Docker에서 제외된다. 기존 데스크톱용 `credentials.json`은 그대로 유지한다. 서버를 다시 시작하고 Google 연결 → 계정 선택 → 읽기 권한 동의 → 수업 선택 → 선택한 수업 연결을 진행한다.

JSON 파일 대신 `GOOGLE_WEB_CLIENT_ID`와 `GOOGLE_WEB_CLIENT_SECRET` 환경변수를 함께 설정해도 된다. 비밀값을 채팅·소스·로그에 붙이지 않는다. `.env.example`의 모든 값은 비워 두었다.

기본 로그인은 프로필과 Classroom 읽기 권한을 요청한다. 첨부 PDF가 필요하면 수업 선택 화면에서 PDF 읽기 권한을 추가 연결한다. 첫 수집은 본문 전체 페이지를 읽고, PDF를 선택한 경우 현재 우선순위 10개 게시물의 첨부를 확인한다. 이미지 PDF의 OCR, HWPX·ZIP 해석은 지원하지 않는다.

## 2. 저장 방식과 공통 분석

웹 상태는 기본 `.local/web/` 아래에 있고 `APP_DATA_DIR`로 변경할 수 있다. Google 인증정보는 Fernet으로 암호화하며 세션 쿠키에는 무작위 값만 저장한다. 쿠키는 HttpOnly/SameSite=Lax이고 HTTPS에서는 Secure 및 `__Host-` 접두사를 사용한다. Google 로그인에는 브라우저에 묶인 일회용 state, PKCE, OIDC nonce와 Google 서명 검증을 사용한다.

모든 데이터·작업·개인 기록 API는 현재 세션의 사용자만 조회한다. 수업 ID를 클라이언트에서 보내도 서버가 해당 Google 계정의 수업 목록으로 접근 권한을 다시 검증한다. 미로그인 방문자는 기존 학교 수집본을 받지 않는다. 정적 파일은 공개 소개 화면의 두 자산만 허용하며 `.local`, `.env`, OAuth JSON을 서빙하지 않는다.

기존 성공 분석을 웹 공통 캐시에 복사하려면 다음 명령을 실행한다.

```powershell
uv run webapp.py seed-cache
```

현재 모델의 성공 분석만 복사하고 Google 토큰·수집본·수업 선택·개인 기록은 복사하지 않는다. 재사용은 해당 사용자가 자기 계정으로 수집한 동일 입력의 캐시 키가 일치할 때만 가능하다. PDF 캐시는 계정별 폴더로 분리한다. 로그인한 사용자가 실제로 읽을 수 없는 PDF 텍스트를 전역 파일 캐시에서 가져오지 않는다.

완료 표시·메모·개인 기한·관심 활동은 웹에서는 계정별 서버 저장, 로컬 HTML에서는 브라우저 저장이다. 작업은 SQLite에 상태를 기록하고 백그라운드로 실행한다. 서버가 중단되면 작업은 interrupted로 남고 AI를 자동 재호출하지 않는다. 현재 프로세스 내 실행기를 사용하므로 **서버 인스턴스 1개·Uvicorn worker 1개**로 운영한다. 여러 인스턴스가 필요하면 외부 작업 큐와 공유 DB로 전환해야 한다.

## 3. AI는 운영자가 켠 뒤 사용자가 선택

기본값은 `WEB_AI_ENABLED=false`다. 본문 날짜 추출과 등록 마감 정리는 AI 없이 사용할 수 있다. 운영자가 기존 BAZE 서버 환경변수와 `WEB_AI_ENABLED=true`를 설정하면 사용자는 ‘공지 AI 정리’를 선택하고 본문·추출 PDF의 전송에 동의한 뒤 실행한다.

1회 최대 3건, 기본 사용자별 하루 3건, 서버 전체 하루 30건의 생성 예약 상한을 둔다. 예약은 DB 트랜잭션으로 잡으며 실패·중단 시에도 보수적으로 소비한 것으로 남긴다. 날짜 경계는 한국 시간이다. `WEB_AI_DAILY_LIMIT`와 `WEB_AI_GLOBAL_DAILY_LIMIT`로 상한을 설정할 수 있다. 모델을 클라이언트가 지정하거나 자동 대체할 수 없다. 불확실·실패 호출을 자동 재시도하지 않는다. 로그인·목록 열기·메모 저장은 생성 호출을 실행하지 않는다.

## 4. 공개 배포

Python 웹 서버를 실행할 수 있는 호스팅 계정이 필요하다. 현재 Render 연결이 제안된 상태이며, 계정 연결과 실제 배포는 아직 완료되지 않았다. [Render FastAPI 배포 안내](https://render.com/docs/deploy-fastapi)에 따라 저장소를 연결하거나 Dockerfile을 사용할 수 있다.

배포 소스는 `dog4e82/school-task-manager` 저장소의 **`moa-classroom-web` 브랜치**를 사용한다. 기존 `main`의 별도 프로그램은 가져오지 않는다. Blueprint도 같은 브랜치를 지정한다. 배포 전 `uv run scripts/package-web.py`로 로컬 인증정보와 소스의 일치 여부를 검사하고, 계정 데이터가 제외된 배포 묶음을 만든다. 검증 명령에 필요한 테스트도 포함한다.

2026-11-06 로컬 확인 결과: 실제 웹 로그인 사용자 1명, 계정별 수집본 1개를 확인했다. 이는 로컬 연결 검증이며, 외부 접속과 두 번째 실제 계정의 연결 성공은 아직 검증하지 않았다. 현재 등록된 Google 콜백은 로컬 주소뿐이다.

`render.yaml`은 영구 디스크가 가능한 **유료 starter 서비스** 예시다. 디스크는 세션·토큰·개인 기록을 재시작 후에도 보존하기 위해 사용한다. 소유자가 계정 연결과 요금제를 확인하기 전에는 이 Blueprint로 유료 리소스를 생성하지 않는다. [Render 영구 디스크 안내](https://render.com/docs/disks)를 확인한다. Docker 빌드는 현재 작업 환경에 Docker가 없어 실제 이미지 빌드로 검증하지 못했다. uv 의존성 설치와 앱 실행·웹 API는 로컬에서 검증한다.

호스팅의 서버 환경변수에 아래를 설정한다.

| 변수 | 설정 |
| --- | --- |
| `APP_BASE_URL` | 실제 HTTPS 사이트 원점. 끝에 경로나 `/` 없이 입력 |
| `APP_DATA_DIR` | 영구 디스크 경로. Render 예시는 `/var/data` |
| `APP_TOKEN_KEY` | 영구 보관하는 Fernet 키. 교체하면 기존 Google 토큰을 복호화할 수 없음 |
| `GOOGLE_WEB_CLIENT_ID` | 웹 앱용 Google OAuth Client ID |
| `GOOGLE_WEB_CLIENT_SECRET` | 웹 앱용 Secret. 호스팅의 비밀 환경변수로 저장 |
| `WEB_AI_ENABLED` | 초기에는 `false`. BAZE 설정 후 명시적으로 활성화 |
| `BAZE_BASE_URL`, `BAZE_API_KEY` | AI를 사용할 때만 설정. 키는 비밀 환경변수 |

로컬 테스트에서 생성한 키를 호스팅 설정으로 복사할 때 터미널에 출력하지 않으려면 다음처럼 클립보드에만 복사할 수 있다. 값은 공유하거나 Git에 저장하지 않는다.

```powershell
Get-Content -Raw .local\web\token-encryption.key | Set-Clipboard
```

Google 웹 클라이언트의 승인된 리디렉션 URI에는 실제 사이트의 `https://사이트주소/auth/callback`도 추가한다. Google Branding의 홈페이지와 개인정보처리방침 주소는 실제 `/`, `/privacy`로 설정하고 운영자 연락처·도메인 소유권도 등록한다.

테스트 모드에서는 승인한 테스트 사용자만 연결할 수 있다. 누구나 연결하는 공개 운영은 Google의 Audience/Publishing 상태를 변경하고 사용하는 범위에 필요한 검증을 진행해야 한다. 학교 관리자의 외부 앱 제한은 별도로 적용될 수 있다. 이 설정은 프로그램 코드나 BAZE 모델 변경으로 우회할 수 없다. [Google 웹 OAuth 안내](https://developers.google.com/identity/protocols/oauth2/web-server), [민감 범위 검증 안내](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)를 참고한다.

## 5. 검증 명령

```powershell
uv run python -m unittest discover -s tests -q
uv run webapp.py check
```

인증·데이터 분리 테스트는 가짜 Google 응답을 사용하며 실계정 로그인을 대신 검증했다고 주장하지 않는다. 실제 웹 OAuth 로그인과 공개 URL 확인은 웹 클라이언트 및 호스팅 계정을 연결한 뒤 수행한다. 접근 로그에는 OAuth code/state나 세션 정보가 남지 않도록 서버의 access log를 끈다.
