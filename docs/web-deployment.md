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

로컬 웹 상태는 기본 `.local/web/` 아래에 있고 `APP_DATA_DIR`로 변경할 수 있다. `DATABASE_URL`을 설정한 무료 웹 배포는 계정 기록과 분석 캐시를 외부 PostgreSQL에 보관한다. Google 인증정보는 Fernet으로 암호화하며 세션 쿠키에는 무작위 값만 저장한다. 쿠키는 HttpOnly/SameSite=Lax이고 HTTPS에서는 Secure 및 `__Host-` 접두사를 사용한다. Google 로그인에는 브라우저에 묶인 일회용 state, PKCE, OIDC nonce와 Google 서명 검증을 사용한다.

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

## 4. 무료 공개 배포

무료 구성은 Render **Free 웹 서비스 + Neon Free PostgreSQL**이다. `render.yaml`은 `plan: free`이며 유료 디스크를 만들지 않는다. Render의 무료 PostgreSQL은 30일 후 만료되므로 장기 저장소로 사용하지 않는다. Render 무료 웹 서비스는 15분 동안 요청이 없으면 중지되고 다음 접속 시 약 1분의 시작 시간이 발생할 수 있다. 무료 사용량 한도도 적용된다. [Render 무료 서비스 안내](https://render.com/docs/free), [Neon 무료 플랜](https://neon.com/pricing).

계정·암호화된 토큰·세션·수집본·개인 기록·작업·분석 캐시는 PostgreSQL의 `moa` 스키마에 보존한다. 원본 PDF 다운로드 캐시만 임시 디스크에 있으며, 추출해 저장한 페이지 텍스트는 계정별 수집본 안에 보존한다. 무료 DB 사용량 한도를 확인하고 웹 서버 인스턴스는 1개로 운영한다.

배포 소스는 `dog4e82/school-task-manager` 저장소의 **`moa-classroom-web` 브랜치**다. 기존 `main`의 별도 프로그램은 가져오지 않는다.

1. [Neon 콘솔](https://console.neon.tech)에서 Free 프로젝트를 만들고 Connect에서 PostgreSQL 연결 문자열을 복사한다. 비밀 연결 문자열을 로컬 Git 제외 파일 `.env`의 `DATABASE_URL`에 저장한다. 채팅이나 Git에 붙이지 않는다.
2. 프로젝트 폴더에서 아래 명령을 실행한다. 실제 DB 검사는 무작위 임시 검증 스키마 안에서 가짜 데이터로만 실행하고 그 스키마를 정리한다. 학교 수집본이나 실제 Google 토큰은 검사에 사용하지 않는다.

```powershell
uv run scripts/check-postgres.py
uv run scripts/prepare-render-env.py
```

두 번째 명령은 기존 웹 OAuth 설정과 암호화 키를 읽어 Git 제외 파일 `.local/render.env`를 만든다. 비밀값을 터미널에 출력하지 않는다. 파일의 값은 Render 환경변수 설정에만 사용한다.

기존 분석을 공통 캐시에 복사해 재사용한다면 `BAZE_BASE_URL`도 Render 환경변수에 같은 값으로 설정한다. 모델·입력·프롬프트와 함께 캐시 식별에 사용되므로 생성 기능을 꺼 둔 경우에도 필요하다. 준비 파일에 이 값이 자동 포함되며 API 키는 포함하지 않는다. `WEB_AI_ENABLED=false`에서는 생성 호출을 실행하지 않는다.

3. Render에서 **New → Blueprint → school-task-manager 연결**을 선택한다. Branch는 `moa-classroom-web`, Blueprint Path는 `render.yaml`이다. 필요한 환경변수 값을 `.local/render.env`에서 설정하고 서비스가 **Free**인지 확인한 뒤 Deploy Blueprint를 실행한다. 유료 워크스페이스 업그레이드나 유료 인스턴스를 선택하지 않는다. [공식 Blueprint 절차](https://render.com/docs/infrastructure-as-code).

| 변수 | 설정 |
| --- | --- |
| `DATABASE_URL` | Neon PostgreSQL 비밀 연결 문자열. TLS 연결 사용 |
| `APP_TOKEN_KEY` | 고정 Fernet 키. `.local/render.env`에서 설정. 교체하면 기존 토큰 복호화 불가 |
| `GOOGLE_WEB_CLIENT_ID` | 웹 앱용 OAuth Client ID |
| `GOOGLE_WEB_CLIENT_SECRET` | 웹 앱용 OAuth Secret |
| `APP_BASE_URL` | Render에서는 플랫폼의 `RENDER_EXTERNAL_URL`을 자동 사용. 사용자 도메인일 때만 명시적으로 설정 |
| `APP_DATA_DIR` | 임시 PDF 캐시 경로 `/tmp/moa`. 계정 기록은 외부 DB에 저장 |
| `WEB_AI_ENABLED` | 초기 `false`. BAZE 설정과 별도 활성화 전에는 생성 호출 없음 |
| `BAZE_BASE_URL` | 기존 분석 캐시 재사용에도 로컬과 동일한 주소 필요 |
| `BAZE_API_KEY` | AI 생성 기능을 활성화할 때만 서버에서 설정 |

Render 환경에서 `DATABASE_URL`을 빠뜨리면 서버가 시작되지 않는다. 임시 SQLite로 자동 대체하여 개인 기록을 잃는 동작을 허용하지 않는다. 기본 로컬 웹 실행과 CLI는 SQLite를 계속 지원한다. 암호화 키는 DB와 별도로 Render 환경변수에 고정 보관한다.

4. 배포 후 실제 HTTPS 주소에 대해 아래 읽기 전용 검사를 실행한다. 이 검사는 실제 Google 로그인 완료를 대신 검증하지 않는다.

```powershell
uv run scripts/check-public-web.py https://실제서비스주소.onrender.com
```

5. Google 웹 클라이언트의 승인된 리디렉션 URI에 실제 사이트의 `https://실제서비스주소.onrender.com/auth/callback`을 추가한다. Google Branding의 홈페이지와 개인정보처리방침 주소는 실제 `/`, `/privacy`로 설정하고 운영자 연락처·도메인 소유권도 등록한다.

테스트 모드에서는 승인한 테스트 사용자만 연결할 수 있다. 누구나 연결하는 공개 운영은 Google Audience/Publishing 상태를 변경하고 필요한 범위 검증을 진행해야 한다. 학교 관리자의 외부 앱 제한은 별도로 적용될 수 있다. [Google 웹 OAuth 안내](https://developers.google.com/identity/protocols/oauth2/web-server), [민감 범위 검증 안내](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification).

2026-11-06 로컬에서는 실제 웹 로그인 사용자 1명, 계정별 수집본 1개를 확인했다. 가짜 데이터로 실제 PostgreSQL 저장·계정 분리·동시 실행 검사도 통과했다. 공개 주소의 실제 로그인과 두 번째 계정 연결은 별도로 검증해야 한다. Docker가 현재 작업 환경에 없어 이미지 빌드는 검증하지 않았다.

## 5. 검증 명령

```powershell
uv run python -m unittest discover -s tests -q
uv run webapp.py check
```

인증·데이터 분리 테스트는 가짜 Google 응답을 사용하며 실계정 로그인을 대신 검증했다고 주장하지 않는다. 실제 웹 OAuth 로그인과 공개 URL 확인은 웹 클라이언트 및 호스팅 계정을 연결한 뒤 수행한다. 접근 로그에는 OAuth code/state나 세션 정보가 남지 않도록 서버의 access log를 끈다.

## 6. 로그인 실패 구분

`/health`의 `oauth_flow_version: 3`으로 새 로그인 처리의 배포 여부를 확인한다. Google에서 돌아온 뒤 실패하면 시작 화면에 다음 코드가 나온다.

| 코드 | 확인할 단계 |
| --- | --- |
| `LOGIN-TOKEN` | 인증 코드 교환: 서버의 웹 OAuth 설정·Google 통신 상태 |
| `LOGIN-IDENTITY` | Google ID 토큰의 서명·대상 클라이언트·nonce·인증된 이메일 검증 |
| `LOGIN-PERMISSIONS` | 요청한 Classroom 읽기 권한이 실제 토큰 응답에 모두 있는지 확인 |
| `LOGIN-STORAGE` | 계정 저장: PostgreSQL 연결·고정 암호화 키 |
| `LOGIN-SESSION` | 계정 저장 이후 세션 발급 |

로그에는 `oauth_callback_failed:단계:예외클래스`만 기록한다. 원래 예외 메시지·토큰 응답·인증 URL은 기록하지 않는다. 과거 PDF 연결 등으로 실제 허용 권한이 요청 목록보다 많아도 필수 권한을 모두 포함하면 허용한다. 실제로 빠진 권한은 거부하며, 전역 `OAUTHLIB_RELAX_TOKEN_SCOPE`를 켜지 않는다.

비공개 DB의 `login_diagnostics`에는 고정된 단계·결과 코드별 누적 횟수와 마지막 발생 시각만 보관한다. 계정 정보·인증 코드·토큰·URL·예외 메시지는 저장하지 않으며 공개 조회 API도 없다. 이 집계가 실패해도 로그인 처리는 계속한다.
