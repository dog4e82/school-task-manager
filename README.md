> 2026-11-08 ?? ? ??: Drive ?? ????? `drive.readonly` ??? ??????. Classroom ?? ??? ?? ???? ?? ??? PDF??? ??? ?????. ?? Drive/PDF ?? ?? ??? ?? ?? ?? ?? ?? ?? ?????. ?? PDF ???? ?? ???? ????. Google Cloud ??? ?????? `drive.readonly`? ???? ??? Classroom???? ??? ?????.

# 모아 · Classroom 과제와 신청 일정

Python 3.13 이상과 uv를 사용합니다. CLI·저장본 UI와 다중 사용자용 FastAPI 웹 서버를 구현했습니다. 웹 OAuth의 실제 연결과 공개 배포에는 별도의 웹 Google 클라이언트 및 호스팅 계정 설정이 필요합니다.

무료 배포 구성은 **Render Free + Neon Free PostgreSQL**입니다. `render.yaml`은 유료 디스크를 만들지 않습니다. 계정·수집본·개인 기록·분석 캐시는 외부 DB에 보존하며, 로컬 실행은 기존 SQLite를 지원합니다. [모아 소개](https://info.moa-classroom.dynv6.net)와 [앱](https://app.moa-classroom.dynv6.net)은 배포되어 있으며, 실제 계정의 로그인·수업 수집을 확인했습니다. 운영자는 Google 브랜딩 게시 완료를 알렸고 데이터 접근 검증은 완료 전입니다. [무료 배포 절차](docs/web-deployment.md)를 참고하세요.

한 공지 안의 서로 다른 과제는 각각 목록에 표시합니다. 과제별 본문·PDF 날짜를 연결하고, 평가 기간·수시 활동·등록 기한을 구분합니다. 본문과 Classroom 시간이 다르면 두 값을 함께 보여 주며, 다른 과제의 기한을 연결한 제안은 확인 필요로 표시합니다. 이 보정은 기존 분석과 원문만 사용하므로 자동 재분석을 실행하지 않습니다.

대회·선택 활동도 게시물 안의 서로 다른 활동을 별도 카드로 보여 줍니다. 같은 날 마감하는 두 활동도 합치지 않고, 각 활동의 관심 표시와 일정의 완료·메모를 따로 저장합니다. 일반 번호형 안내는 독립된 행동·날짜가 있는 구간을 분리하며 한 과제의 제출 형식·준비물 목록은 그대로 둡니다. [여러 항목 표시와 검증](docs/multiple-items.md)을 참고하세요.

웹 AI는 운영자가 활성화한 뒤 학교 계정에서 사용합니다. 일일 분석 건수 제한 없이 미분석 자료를 처리하고, **호출 전 서비스 잔액이 2,000크레딧 미만이거나 확인되지 않으면 새 생성을 멈춥니다.** 기존 결과와 원문은 계속 볼 수 있습니다. 처음 연결할 때 PDF 읽기를 권장하며, 전송 동의 후 수집→첨부 확인→AI 정리를 이어서 실행할 수 있습니다. 본문은 먼저 열리고 정리는 백그라운드에서 계속됩니다. 지난 기한은 기본 목록에서 숨기고 ‘지난 기한’에서 다시 확인합니다. [현재 운영 방식](docs/school-analysis.md)을 참고하세요.

## 계정별 웹 버전 실행

```powershell
uv run webapp.py check
uv run webapp.py serve
```

`http://127.0.0.1:8000`에서 Google 로그인 → 수업 선택 → 연결 → 통합 대시보드로 진행합니다. 기존 데스크톱 OAuth JSON을 그대로 웹 로그인에 사용하지 않습니다. Google Cloud에서 **웹 애플리케이션** 클라이언트를 만들고 리디렉션 URI `http://127.0.0.1:8000/auth/callback`을 등록한 뒤 JSON을 Git 제외 파일 **`credentials.web.json`**으로 저장하고 서버를 다시 시작하세요. 비밀값을 채팅에 올리지 않아도 됩니다.

수업·수집본·개인 메모·완료·관심 활동은 계정별로 분리하고, Google 토큰은 서버에서 암호화합니다. 첫 로그인에는 기존 계정의 학교 데이터를 대신 보여 주지 않습니다. 목록은 짧은 행으로 표시하고, 과제·대회·공지 행을 클릭하면 바로 아래에 원문 본문이 펼쳐집니다. 본문은 추가 클릭 없이 전체가 보이며, 기한·첨부·개인 기록은 본문 아래에 표시합니다. 근거·분석 설명 영역은 화면에 표시하지 않습니다. [웹 실행·Google 공개 설정·배포 안내](docs/web-deployment.md)에 운영 설정을 정리했습니다.

## 저장 데이터로 UI 보기 — 추가 분석 없음

```powershell
uv run ui.py --open
```

흰색·회색 중심의 데스크톱 대시보드를 `.local/classroom-ui.html`에 생성하고 브라우저로 엽니다. 작은 요약 숫자와 7일 기한 줄, 낮은 일정 행으로 표시하며 본문은 행 바로 아래에 펼쳐집니다. 큰 그림·요약 카드·초록색 테마는 제거했습니다. 이후에는 HTML 파일을 직접 열어도 됩니다. 기존 수집본·분석 DB만 읽으며 Classroom/Drive/BAZE API를 호출하지 않습니다. 원문 데이터가 들어간 HTML은 `.local/` 아래에 두어 Git에서 제외합니다. UI 소스는 `web/index.html`, `web/app.css`, `web/app.js`이고 Python 데이터 연결은 `ui_data.py`입니다. Node 빌드나 추가 패키지 설치가 필요 없습니다. 현재 디자인은 데스크톱 1280/1440/1920px 기준이며 휴대전화용 레이아웃은 제공하지 않습니다.

지원 동작은 과제 대시보드, 수업별 필터, 키워드 검색, 기한·수업·제목 정렬, 월간 캘린더와 날짜별 목록, 공지·자료 본문 펼치기, 첨부 원문 링크, 수동 완료 표시, 개인 메모·개인 기한입니다. 완료와 개인 기록은 해당 브라우저의 로컬 저장소에만 남으며 실제 Classroom 제출 상태나 공통 원문은 바꾸지 않습니다. 기록을 저장한 뒤에도 공식 기한과 원래 기한 표현은 펼친 본문 아래에서 확인할 수 있습니다.

기본 대시보드는 **과제·대회 접수·교내 신청 중 기한이 남아 있는 항목을 함께 마감순**으로 보여 줍니다. 7일 보드와 캘린더도 같은 통합 기한을 사용합니다. 하나의 공지에 교내 신청과 외부 접수 마감이 있으면 별도 일정으로 표시합니다. 기한이 없거나 지난 항목은 ‘전체 일정’에서 확인합니다. 행을 누르면 바로 아래에 본문 전체가 표시되고, 다시 누르거나 ‘접기’를 누르면 닫힙니다. **원문** 또는 **Classroom에서 열기**는 원래 게시물을 새 탭에서 엽니다. 학교 계정으로 로그인한 브라우저에서 확인하세요. 공지·자료 화면은 수집한 게시물 전체를 연결합니다. 표시 데이터는 내보내기 시점의 저장본이며, UI의 클릭·검색·필터가 새 분석을 실행하지 않습니다.

이 명령은 개인 저장본을 보는 로컬 미리보기입니다. 로그인·계정별 서버 저장은 상단의 웹 버전 실행 방법을 사용하세요. 로컬 HTML의 브라우저 저장 공간을 지우면 로컬 완료·메모 기록도 지워집니다. `uv run ui.py --as-of 2026-11-06`으로 특정 한국 날짜를 기준으로 화면을 생성할 수 있습니다.

### 대회·공모·선택 활동과 신청 기한

왼쪽 **대회·선택 활동**에서 신청할 수 있는 활동 안내를 과제와 별도로 봅니다. 대회·공모, 탐구·연구, 체험·특강 아이콘으로 구분하며, 관심 활동을 브라우저에 저장할 수 있습니다. 외부 신청 마감, 교내 참여 의사 전달 기한, 행사 일정을 각각 표시합니다. 행사일을 신청 마감으로 쓰거나 Classroom 과제 마감을 선택 활동의 신청 기한으로 대신 넣지 않습니다.

원문에 명시된 신청 날짜와 참여 의무는 별도로 확인합니다. ‘이번 주 금요일’ 같은 상대 날짜는 게시일 기준 추정과 원문 표현을 함께 보여 줍니다. 지난 추정 기한은 ‘지난 기한’에서 보되 확정 마감이라고 표시하지 않습니다. AI 분석이 없는 안내는 **안내 후보·분석 대기**, 날짜가 없는 경우는 **원문 확인 필요**로 표시합니다. 생기부 기재 여부를 자동 판단하거나 보장하지 않습니다.

신청·접수 기간은 `notice_dates.py`에서 본문과 이미 추출된 PDF 텍스트로 한 번 더 검증합니다. 예를 들어 `2026. 10. 8.(목) 18:00~11. 2.(월) 18:00`은 같은 기간의 연도를 이어 받아 **2026-11-02 18:00 (한국시간)**을 접수 마감으로 잡습니다. 시작일을 마감으로 쓰거나 시작 시각을 종료 시각에 복사하지 않습니다. `이번주 금요일`은 게시일을 기준으로 계산하되 확정하지 않으며, 연도 없는 단독 날짜도 추정으로 표시합니다. 명시된 신청 날짜는 AI가 아직 처리하지 않은 공지에서도 **원문 날짜 확인**으로 사용할 수 있습니다. 참가 의무·대상까지 확인했다는 뜻은 아닙니다. 같은 종류의 날짜에서 본문과 PDF의 명시 시각이 충돌하면 확인 필요로 남깁니다. 기존 성공 캐시를 다시 생성 호출하지 않고 화면을 내보낼 때 보정합니다.

[Classroom 과제 API](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork)는 `dueDate`·`dueTime`을 제공하지만, [자료 게시물 API](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWorkMaterials)는 본문과 원문 링크를 제공하고 신청 마감 필드를 따로 제공하지 않습니다. 등록 과제 마감은 그대로 보존하며, 자료의 접수 마감은 본문 근거에서 별도로 추출합니다.

신청·모집 안내 후보만 소량 추가 분석하고 화면에 반영하려면 다음 두 명령을 차례로 실행합니다. 첫 번째만 BAZE 생성 호출을 수행하며 실제 과금될 수 있습니다. 모델은 기존 `gpt-6.1-sol`을 그대로 사용하고, 현재 입력과 일치하는 성공 캐시는 재사용합니다.

```powershell
uv run classroom.py analyze --focus opportunities --limit 3
uv run ui.py --open
```

전송 없이 대상 건수만 확인하려면 `uv run classroom.py analyze --focus opportunities --limit 3 --dry-run`을 사용합니다. 학교의 최신 게시물까지 가져오려면 별도로 `uv run classroom.py sync --pdf-limit 40`을 먼저 실행합니다. 이때 현재 접근 가능한 자료만 수집하며, 이미지 PDF의 OCR이나 HWPX 본문은 지원하지 않습니다.

디자인 지침은 [Anthropic의 공식 frontend-design 스킬](https://github.com/anthropics/skills/tree/main/skills/frontend-design)을 설치해 적용했습니다. 앱의 분석 모델이나 전역 모델 설정은 변경하지 않았습니다. UI 디자인 결정은 `docs/design.md`에 기록했습니다.

## 수집한 게시물을 AI로 분석

### 과제 중심 결과 보기

```powershell
uv run task_report.py
```

`.local/analysis-results.html`을 브라우저로 열면 필수·대상 조건이 있는 할 일, 기한·의무 확인 항목, 선택 활동 순으로 표시합니다. 지난 기한 항목·참고자료·기한 미정의 미분석 등록 항목은 접어 둡니다. 상세 본문·PDF 근거와 원문 링크는 각 항목에서 펼칠 수 있습니다. 현재 기본 업그레이드 모델과 현재 입력의 캐시 키가 일치하는 분석만 사용하며 이전 Gemma 결과를 대체 결과로 섞지 않습니다. 아직 AI가 처리하지 않은 등록 과제는 ‘AI 분석 대기’로 표시하고, 제출 완료 여부나 필수 여부를 추측하지 않습니다. `uv run export_results.py`도 같은 보고서를 생성합니다.

보고서는 한국 날짜를 기본으로 사용하며, 특정 기준일로 재현하려면 `uv run task_report.py --as-of 2026-11-05`를 실행합니다. 보고서 생성 자체는 API를 호출하지 않습니다.

대역폭이 제한된 경우 본문 전체를 먼저 저장하고 현재 과제·최근 안내 일부의 PDF만 우선 확인할 수 있습니다.

```powershell
uv run classroom.py sync --pdf-limit 40
```

이때 나머지 첨부는 `not_read`로 남고 전체 PDF 완료로 표시하지 않습니다. PDF 수집 전에 본문 수집본을 저장하며, 첨부 확인 중에도 주기적으로 중간 저장합니다. AI 분석 순서는 마감이 다가오는 등록 과제, 최근 제출·신청 안내, 그 밖의 게시물 순입니다. 이 우선순위는 AI가 필수 여부나 제출 완료 여부를 판정했다는 뜻이 아닙니다.

모델을 직접 학습하거나 파인튜닝하지 않습니다. BAZE API에 분석 규칙·예시와 게시물 제목/상세 본문·첨부 PDF 추출 텍스트를 보내고 결과를 검증합니다. 기본 모델은 `gpt-6.1-sol`로 업그레이드했습니다. 기존 `.env`를 그대로 사용하며 PDF 추출용 `pypdf`를 uv 의존성에 추가했습니다. 매 실행 시 공식 `/models/`에서 가용성과 단가를 확인하며, 모델이 없으면 자동 대체하지 않습니다. 실계정 조회 단가는 100만 토큰당 입력 USD 2, 출력 USD 10이었으며 기존 Gemma보다 높습니다. 기본 생성 상한 3회와 캐시는 유지합니다.

사진과 같은 **‘새 자료’ 카드의 상세 본문**은 `courseWorkMaterials.list`의 `description`에서 수집합니다. 화면 카드를 브라우저로 클릭하거나 스크래핑하지 않아도 상세 글이 포함됩니다. 기존 수집본은 과제·공지 두 종류뿐이므로 아래 순서로 한 번 다시 수집하세요.

1. 기존 Google Cloud 프로젝트에서 [Google Drive API 사용](https://console.cloud.google.com/apis/library/drive.googleapis.com)을 누릅니다.
2. `uv run classroom.py sync`를 실행하고 학교 계정으로 추가 읽기 권한에 동의한 뒤 수업을 선택합니다. Google Auth platform의 Data Access에도 아래 추가 범위를 등록합니다.

   ```text
   https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly
   https://www.googleapis.com/auth/drive.readonly
   ```

3. 사진의 게시물만 확인하려면 다음 명령을 실행합니다.

   ```powershell
   uv run classroom.py analyze --title "AI경진대회" --limit 1
   uv run classroom.py ai-tasks --title "AI경진대회"
   ```

Drive 읽기 권한은 Google 동의 화면에서 전체 Drive 읽기 범위로 보이지만, 이 코드는 수집한 Classroom 게시물에 연결된 파일 ID에만 `files.get`/다운로드를 수행합니다. Drive 전체 파일 검색이나 쓰기는 하지 않습니다. 공개 웹서비스로 전환할 때는 Drive 범위에 필요한 검증 절차를 별도로 다뤄야 합니다.

```powershell
uv run classroom.py analyze
```

이 명령은 **최신 미분석 게시물 최대 3개**를 분석합니다. 동일 명령을 다시 실행하면 성공한 결과를 재사용하고 다음 미분석 게시물로 진행합니다. 전체 수집은 508개이더라도 3개 분석 후 전체 완료로 표시하지 않으며, 처리·캐시·보류·실패 건수를 출력합니다. 수집 누락 수업도 별도로 안내합니다. 최초 실제 연결 검증은 `--limit 1`로 한 게시물만 호출합니다.

추가로 사용할 명령:

```powershell
# 실제 전송·생성 없이 대상 건수만 확인
uv run classroom.py analyze --dry-run

# 이번 실행 신규 생성 상한을 명시적으로 변경 (과금 가능)
uv run classroom.py analyze --limit 10

# 저장한 결과만 보기: 네트워크 요청과 생성 없음
uv run classroom.py ai-tasks
uv run classroom.py ai-tasks --limit 100

# 다른 모델을 선택한다면 분석과 결과 조회에서 같은 모델 ID 사용
uv run classroom.py analyze --model '조회한-실제-모델-ID' --limit 1
uv run classroom.py ai-tasks --model '조회한-실제-모델-ID'
```

기본 전송 범위는 분석할 게시물의 제목·상세 본문, 원래 게시 시각과 과제 API 마감, 게시물을 구분하는 ID, 해당 게시물에 첨부된 PDF의 페이지별 추출 텍스트입니다. OAuth 토큰, BAZE 키, 학생 명단, API 원본 전체는 모델 입력에 포함하지 않습니다. 본문·PDF에 적힌 개인정보도 해당 텍스트와 함께 BAZE로 전송될 수 있습니다. 이 프로그램은 모델 학습 데이터를 만드는 기능이 없으며 외부 제공사의 데이터 보관 정책을 별도로 보증하지 않습니다.

후속 공지 연결을 분석하려면 아래 **별도 옵션을 명시적으로 선택**하세요. 같은 수업의 이전 게시물 최대 3개에서 제목과 본문 앞부분 최대 1,200자씩을 추가 전송합니다. 기본 명령은 이전 게시물을 보내지 않습니다.

```powershell
uv run classroom.py analyze --with-context --limit 3
uv run classroom.py ai-tasks --with-context
```

연결은 현재 공지의 원문 인용과 같은 수업의 제공된 후보 ID가 확인된 경우만 검토 후보로 저장합니다. 연결 후보가 나와도 기존 과제 마감을 자동 변경하거나 게시물을 자동 병합하지 않습니다. 이전 후보가 최대 3개이므로 모든 후속 관계를 찾는 기능은 아닙니다.

분석과 검증 규칙:

- `task_status`: `required`(필수 지시), `optional`(선택 활동), `reference`(참고자료), `unknown`(확인 필요)
- `deadline_status`: `confirmed`와 `unknown`을 과제 여부와 별도로 관리
- 제출 의무와 마감 근거는 각각 원문에 존재하는 짧은 연속 인용문이어야 함
- 명시된 제출 지시 없이 필수로 판단하거나, 발표자/참여자 등 대상 조건이 있으면 확인 필요로 낮춤
- 날짜의 해당 문장에 제출/신청 기한이 있고 연·월·일이 명시된 경우에 근거가 확인된 날짜로 저장. 신청기간은 종료일을 신청 마감으로 분리. 공개·게시일은 제출 마감으로 확정하지 않음
- 연도 없는 날짜와 상대 날짜도 `proposed_deadline`과 `deadline_expression`에 AI 제안을 남겨 답을 먼저 제시. `이번 주 금요일`, `다음 주 금요일`, `오늘`, `내일`은 원래 게시일의 한국 시간 기준으로 계산하되 확정 마감과 구별. 대상 조건도 별도로 표시
- 원래 Classroom API 마감은 별도로 유지. AI 날짜와 충돌하면 `classroom_deadline_conflict`로 표시하며 덮어쓰지 않음
- JSON·응답 길이·인용 검증이 실패하면 자동으로 다시 생성하지 않음

결과는 **할 일·분류·기한 제안 → 원문 인용·PDF 파일명/페이지·원문 링크 → 필요한 부분의 ‘확인 필요’** 순서로 표시합니다. 모든 항목에 `review_required: true`를 붙이지 않습니다. 근거가 충족되면 false이고, 인용 누락·의무 불명확·상대 날짜·등록된 마감과 충돌하는 경우만 true입니다. 기한 미정은 과제 여부와 별도로 표시합니다. 모델 제안(`proposed_task_status`, `proposed_deadline`, `action`)과 검증된 값(`task_status`, `deadline`)을 함께 보관하므로, 코드가 날짜를 확정하지 못해도 제안과 원래 표현이 사라지지 않습니다. 구두 안내·제출 완료 여부·모든 후속 관계의 자동 확정은 아직 포함하지 않습니다.

텍스트 PDF는 페이지별로 추출하고 PDF 파일/페이지를 근거로 표시합니다. 이미지/스캔 PDF의 텍스트가 비면 `ocr_needed`, 암호 PDF는 `encrypted`, 읽기 권한 부족은 `access_denied` 등으로 표시하며 읽은 것으로 처리하지 않습니다. OCR, HWP/HWPX, ZIP 내부와 외부 웹 링크 자동 수집은 이번 구현에 포함하지 않습니다. PDF는 파일당 20 MiB, 최대 50페이지, 추출 텍스트 20만 자 상한이며 일부만 읽은 파일은 `partial`로 표시합니다. 본문과 PDF를 합친 모델 입력 JSON이 60,000자를 넘으면 잘라 보내지 않고 보류합니다. 생성 출력은 4,096토큰 상한이며 빈 출력·잘린 출력은 실패로 기록합니다.

캐시 및 재시도:

- `.local/classroom/analysis.sqlite3`에 본문·PDF 페이지 텍스트/버전·프롬프트·모델·제공자 URL·출력 제한·추가 문맥의 해시별 결과를 저장합니다. 동일 입력이면 재호출하지 않고 바뀐 입력만 새 분석 대상입니다. 키 자체는 해시 입력이나 DB에 저장하지 않습니다. PDF 추출 결과는 `.local/classroom/pdf-cache/`에 Drive 수정 시각/버전/체크섬별로 재사용합니다. 다운로드할 때마다 현재 접근 권한과 버전 메타데이터를 다시 확인합니다.
- 본문이 바뀌거나 삭제된 게시물의 예전 결과는 현재 결과 목록에 섞지 않습니다. 예전 DB 행은 남아 있어도 현재 입력과 일치하는 결과만 표시합니다.
- 실패·중단·검증 실패도 기록해 다음 기본 실행에서 과금 요청을 자동 반복하지 않습니다. 실제 재시도가 필요할 때만 `uv run classroom.py analyze --retry-failed --limit 1`을 실행하세요. 처리 여부가 불확실한 요청은 재과금될 수 있습니다.
- 정상 실행 중인 동일 입력은 중복 호출하지 않습니다. 프로세스가 강제 종료되어 `processing`으로 남은 항목도 자동 재전송하지 않습니다.
- 각 호출의 제공된 `usage`·`billing`, 실행 전후 잔액을 저장·표시합니다. `billing`이 없으면 차감 크레딧을 추정하지 않습니다. `estimated_cost`는 API가 제공한 추정값 그대로이며 확정 차감 크레딧으로 해석하지 않습니다. 잔액 차이 역시 동시 사용·반영 지연으로 확정 비용이 아닙니다.

## Classroom이 연결됐다면 — 과제·공지 수집

```powershell
uv run classroom.py sync
```

기존 로그인에 과제·공지 읽기 권한이 없으면 브라우저가 열려 추가 동의를 요청합니다. 학교 계정으로 로그인하고 요청한 읽기 권한을 모두 허용하세요. 새 로그인 후에는 계정 혼동을 막기 위해 수업을 다시 선택합니다. 터미널에 번호 목록이 나오면 `all` 또는 `1,3`처럼 입력합니다. 이후에는 같은 명령으로 선택한 수업을 새로 수집하며, 토큰이 유효하면 추가 로그인하지 않습니다.

추가 OAuth 범위는 다음과 같습니다. Google Cloud의 Data Access(데이터 액세스)에서 앱의 범위에 추가하세요. 학교 관리자의 앱 허용 정책이 적용될 수 있습니다.

```text
https://www.googleapis.com/auth/classroom.student-submissions.me.readonly
https://www.googleapis.com/auth/classroom.announcements.readonly
https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly
https://www.googleapis.com/auth/drive.readonly
```

공식 Classroom API의 게시된 과제·질문, 공지, 자료 게시물(`courseWorkMaterials`)을 `nextPageToken`이 끝날 때까지 모두 읽습니다. 현재 계정이 볼 수 있는 내용만 조회합니다. `.local/classroom/snapshot.json`에 원문 API 응답과 정리한 항목을 함께 저장하고, 과제·질문은 마감순 및 원문 링크와 함께 출력합니다. 마감은 API의 `dueDate`와 `dueTime`(UTC)을 한국 시간으로 바꿉니다. 마감 미등록 항목은 마지막에 둡니다. `sync` 자체는 본문 의미를 해석하지 않으며 `analyze`가 별도로 과제·선택 활동·기한을 제안합니다. 학생 제출물이나 성적은 별도 조회하지 않습니다.

수업별 `403` 중 Google이 `The caller does not have permission`을 반환하면 해당 수업의 해당 종류 게시물만 미수집으로 기록하고 다른 수업과 공지는 계속 수집합니다. 실제 연결 점검에서 학생으로 참여한 16개 수업의 과제·공지는 읽혔지만 교사로 참여한 1개 수업의 과제는 학생용 권한으로 거부된 사례를 확인했습니다. 교사용 권한은 자동 추가하지 않습니다.

일부 접근 거부 시 결과에 `complete: false`와 수업/종류별 `failures`를 기록하고 터미널에도 **부분 수집 완료**와 미수집 항목을 명시합니다. 종료 코드는 `2`입니다. 한 종류의 조회가 중간 페이지에서 거부되면 그 종류는 전체 미수집으로 처리합니다. 전역 권한 부족(`ACCESS_TOKEN_SCOPE_INSUFFICIENT`), API 비활성화, 미분류 오류, 네트워크 오류 등은 수집을 중단하고 기존 파일을 덮어쓰지 않습니다. 이때 오류에는 API 종류와 허용된 오류 코드만 표시하며 응답 원문은 출력하지 않습니다.

새 계정 로그인/재동의 시에는 이전 계정의 선택과 수집 파일을 먼저 지우고 다시 수집합니다. `sync`는 과제·공지·자료 게시물과 연결된 PDF를 로컬에 수집하며 BAZE 호출은 없습니다. 실제 AI 전송은 `analyze`에서만 수행합니다. 일반 동기화 시 수집 파일은 최신 조회 결과로 교체하며 변경 이력 누적은 후속 단계입니다.

저장한 과제를 네트워크 요청 없이 다시 보려면:

```powershell
uv run classroom.py tasks
```

Google이 `classroom.coursework.me.readonly` 요청을 `classroom.student-submissions.me.readonly`로 반환해 `Scope has changed` 예외가 발생한 실계정 사례에 맞춰, 코드는 반환된 읽기 권한 이름을 직접 요청합니다. 권한 비교를 끄는 `OAUTHLIB_RELAX_TOKEN_SCOPE`는 설정하지 않습니다. 두 범위의 공식 설명은 [Google OAuth 범위 목록](https://developers.google.com/identity/protocols/oauth2/scopes#classroom)에 있으며, [Google OAuth 안내](https://developers.google.com/identity/protocols/oauth2)도 API가 요청과 다른 범위 이름을 반환할 수 있다고 설명합니다. 실제 과제 조회 가능 여부는 API 수집 결과로 확인합니다.

읽기 권한을 일부만 허용했거나 다시 로그인해야 한다면:

```powershell
uv run classroom.py sync --reauth
```

공식 근거: [과제·질문 목록](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork/list), [공지 목록](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.announcements/list), [자료 상세 본문 및 페이지 처리](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWorkMaterials/list), [Drive 파일 다운로드](https://developers.google.com/workspace/drive/api/guides/manage-downloads), [Drive 읽기 범위](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [PDF 텍스트 추출과 이미지 PDF의 한계](https://pypdf.readthedocs.io/en/stable/user/extract-text.html), [마감 필드의 UTC 기준](https://developers.google.com/workspace/classroom/reference/rest/v1/courses.courseWork).

## Classroom 연결 — 처음 한 번만 설정

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 새로 만듭니다. 이름은 `classroom-task-manager`로 하면 됩니다. 개인 Google 계정으로 프로젝트를 만들었더라도 실제 Classroom 로그인에서는 학교 계정을 선택할 수 있습니다. 학교에서 프로젝트 생성이 막혀 있다면 개인 계정에서 생성하세요.
2. [Google Classroom API](https://console.cloud.google.com/apis/library/classroom.googleapis.com)를 열고 방금 만든 프로젝트에서 **사용**을 누릅니다.
3. **Google Auth platform → Branding(브랜딩) → 시작하기**에서 앱 이름과 본인 연락 이메일을 입력합니다. **Audience(대상)는 External(외부)**로 정하고 테스트 상태를 유지합니다. 이후 **Audience → Test users(테스트 사용자)**에 **Classroom을 사용하는 학교 이메일**을 추가합니다. **Data Access(데이터 액세스) → 범위 추가 또는 삭제**에서 아래 범위 하나를 추가합니다.

   ```text
   https://www.googleapis.com/auth/classroom.courses.readonly
   ```

4. **Google Auth platform → Clients(클라이언트) → 클라이언트 만들기 → 데스크톱 앱**을 선택합니다. 생성된 OAuth 클라이언트의 **JSON을 다운로드**하고 프로젝트 폴더 `C:\Users\hahah\classroom-task-manager`에 **`credentials.json`**이라는 이름으로 저장합니다. 서비스 계정 키나 웹 애플리케이션 유형을 선택하지 마세요. 내려받은 파일의 내용을 채팅으로 보내지 않아도 됩니다.

설정이 끝나면 터미널에서:

```powershell
uv run classroom.py connect
```

브라우저에서 **학교 계정**으로 로그인하고 수업 조회를 허용합니다. 터미널에 수업 목록이 나타나면 `1,3`처럼 번호를 입력하거나 `all`로 전체를 선택하세요. Enter만 누르면 선택을 취소합니다. 활성·보관 수업 모두 조회하며 `nextPageToken`이 끝날 때까지 모든 페이지를 읽습니다. 조회 실패 시 일부 목록을 저장하지 않습니다.

이후 사용할 명령:

```powershell
uv run classroom.py courses
uv run classroom.py connect
uv run classroom.py connect --reauth
```

순서대로 수업 목록만 보기, 선택 변경, 계정 변경/재동의입니다. 로그인 토큰은 `.local/classroom/token.json`, 선택한 수업은 `.local/classroom/selected_courses.json`에 저장합니다. 새로 로그인하면 이전 계정의 수업 선택은 지웁니다. `credentials.json`, `client_secret*.json`, `token.json`, `.local/`은 모두 Git에서 제외하며 토큰·인증코드·OAuth URL·API 오류 원문은 터미널에 출력하지 않습니다. 토큰 파일은 개인 PC에서 사용하는 로컬 파일이며 암호화 저장이나 공개 웹서비스의 사용자 세션을 구현한 것은 아닙니다. 이 연결·목록 조회 명령은 BAZE를 호출하지 않습니다.

오류가 발생하면:

- **`credentials.json이 없습니다`**: 파일명과 저장 위치를 확인하세요. JSON 내용은 공유하지 마세요.
- **`access_denied` / 테스트 사용자 제한**: Audience의 Test users에 실제 로그인할 학교 이메일이 들어 있는지 확인하세요.
- **`admin_policy_enforced` / 학교 관리자 차단**: 학교 관리자가 이 OAuth 클라이언트를 허용해야 합니다. 개인 계정으로 로그인해도 학교 수업에 접근할 수 있는 것은 아닙니다.
- **`403`**: 같은 Cloud 프로젝트에서 Classroom API를 활성화했는지, 학교가 해당 앱과 Classroom 접근을 허용하는지 확인하세요.
- **수업 0개**: 실제 Classroom 수업에 참여 중인 계정으로 `connect --reauth`를 실행하세요.
- **토큰 만료/취소 또는 로그인 3분 초과**: `uv run classroom.py connect --reauth`로 다시 시도하세요. 테스트 상태의 외부 OAuth 앱은 재동의가 필요할 수 있습니다.

실제 학교 계정 연결은 위 설정과 브라우저 동의 후에 검증할 수 있습니다. 공개 웹서비스 전환 시에는 웹 앱용 OAuth 클라이언트, HTTPS 콜백, 사용자별 토큰 보관, 필요한 검증 절차를 따로 구현해야 합니다.

공식 근거: [Python OAuth 시작 안내](https://developers.google.com/workspace/classroom/quickstart/python), [OAuth 동의·테스트 사용자 설정](https://developers.google.com/workspace/guides/configure-oauth-consent), [수업 목록·페이지 처리](https://developers.google.com/workspace/classroom/reference/rest/v1/courses/list), [학교의 API 접근 관리](https://support.google.com/edu/classroom/answer/6253304).

## 설치와 설정 (PowerShell)

```powershell
uv sync --locked
Copy-Item .env.example .env
```

생성한 `.env`를 로컬 편집기로 열어 아래 두 값을 입력합니다. `.env.example`의 값은 비어 있으며 `.env`는 Git에서 제외됩니다.

- `BAZE_BASE_URL`: 공식 문서의 `https://api.baze.co/v1/gateway`
- `BAZE_API_KEY`: 해당 배포의 BAZE API Gateway에서 발급한 키

동일 이름의 로컬 환경변수도 지원하며 환경변수가 `.env`보다 우선합니다. 키를 채팅·명령 인수·코드·로그에 넣지 마세요. Codex 모델, 전역 설정, 셸 프로필은 변경하지 않습니다.

## 조회 (생성 요청 없음)

```powershell
uv run main.py --help
uv run main.py check
uv run main.py balance
uv run main.py models
uv run main.py pricing
```

`check`는 모델 목록 조회 성공 후 잔액을 조회합니다. `models`와 `pricing`은 같은 공식 `/models/` 응답에서 모델별 `pricing`과 계정의 환산 정보를 표시합니다. 단가와 단위는 서버 응답 그대로 출력하며, 누락되면 미제공으로 표시합니다. 서로 다른 단위나 누락된 가격으로 최저가를 추정하지 않습니다. 반환된 llm 모델의 입력·출력 단가를 확인하고 저렴한 Chat Completions 지원 모델을 직접 선택하세요. API 오류 본문, 요청 헤더, 키, Base URL은 출력하지 않습니다. 리다이렉트도 따라가지 않습니다.

## 선택 모델로 모의 공지 1회 분석 (실제 과금 가능)

먼저 `check`를 성공시킨 뒤 `models`에서 확인한 실제 모델 ID를 입력합니다.

```powershell
uv run main.py analyze --model '선택한-실제-모델-ID'
```

이 명령은 모델 목록과 호출 전 잔액 조회에 성공해야만 `POST /chat/completions/`를 **한 번** 수행합니다. 조회되지 않은 모델, llm 이외 모델, Codex 모델은 거부합니다. 모델을 자동 선택하지 않습니다. 명령을 다시 실행하면 다시 과금될 수 있습니다.

고정 입력: “과학 보고서를 제출하세요. 마감은 추후 공지합니다. 심화 문제 풀이는 선택 활동입니다. 참고 영상은 2026년 11월 10일 공개됩니다.”

프롬프트는 과제 여부와 마감 확정 여부를 분리하고, 원문 근거와 미확정 마감의 null 표현을 요청합니다. AI 출력은 검토용으로만 표시하며 실제 과제나 날짜로 저장·확정하지 않습니다. 출력 상한은 512토큰이며 추론 모델에서는 출력이 비거나 잘릴 수 있습니다. 이 경우에도 재시도하지 않습니다. 연결 테스트를 위해 일반 텍스트 모델을 선택하는 편이 적합합니다.

표시 항목:

- 선택 모델과 제공된 단가
- 호출 전후 크레딧: 월간 할당, 구매, 조직 부여, 합계
- 생성 응답의 `usage`와 `billing` (공식 차감값은 `billing.deducted_credit`)
- 합계 잔액의 관측 감소량: 동시 사용, 월간 갱신, 반영 지연 때문에 이번 호출의 확정 비용으로 간주하지 않음

`billing` 또는 사용량이 없으면 추정하지 않습니다. 생성 실패·시간 초과에도 호출 후 잔액을 조회하며 자동 재시도는 없습니다. 호출 후 조회 실패는 별도로 표시합니다. 네트워크 오류는 생성이 처리되지 않았다는 증거가 아니므로 `balance`로 다시 확인하세요. 화면의 월간 5,000크레딧이 API에도 적용되는지와 실제 차감량은 **실계정 응답으로 아직 검증하지 않았습니다**.

동일 공지 재사용 정책은 후속 단계에서 저장소와 함께 구현할 사항입니다. 이번 명령은 호출·과금 관측용이므로 캐시 없이 명시적으로 실행할 때마다 1회 요청합니다.

## 로컬 검증

```powershell
uv run python -m unittest discover -s tests -v
```

실제 API와 과금 없이 모의 응답으로 검증합니다.

## 참고한 BAZE 공식 문서

- [설정 안내](https://docs.factchat.kr/agent-setup/prompt.md): 연결 URL과 인증 방식만 참고
- [잔액](https://docs.factchat.kr/docs/general/api-gateway/reference/credits.md)
- [모델 목록](https://docs.factchat.kr/docs/general/api-gateway/getting-started/models.md)
- [단가 및 billing](https://docs.factchat.kr/docs/general/api-gateway/reference/pricing.md)
- [Chat Completions](https://docs.factchat.kr/docs/general/api-gateway/reference/chat-completions.md)

2026-11-05에 위 문서를 확인했습니다. `/openapi.json`은 두 번 모두 HTTP 502여서 공식 개별 레퍼런스를 기준으로 구현했습니다. 실계정 키 없이 실제 연결·크레딧 적용·과금 성공을 주장하지 않습니다.
