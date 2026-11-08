"""Public introduction and authenticated course selection, without school sample data."""

import html
import json


SUPPORT_EMAIL = "dog4e82@gmail.com"


def page(title, content, bootstrap=None, description=""):
    data = json.dumps(bootstrap or {}, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    page_title = title if title == "모아" else title + " · 모아"
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="description" content="{html.escape(description, quote=True)}">
    <title>{html.escape(page_title)}</title><link rel="stylesheet" href="/assets/account.css"></head>
    <body><header><a class="logo" href="/" aria-label="모아 홈">▦ <span>모아</span></a><a href="/privacy">개인정보처리방침</a></header><main>{content}</main>
    <script type="application/json" id="account-data">{data}</script><script src="/assets/account.js" defer></script></body></html>'''


def landing(configured, error=None, public_origin=""):
    errors = {"google_denied": "Google 연결이 완료되지 않았어요. 계정과 읽기 권한을 확인하고 다시 연결하세요.",
              "oauth_failed": "로그인 연결을 확인하지 못했어요. 다시 시작해 주세요.",
              "oauth_token_failed": "Google 인증을 마무리하지 못했어요. 연결 오류 코드: LOGIN-TOKEN. 운영자가 서버의 Google 연결 설정과 통신 상태를 확인해야 합니다.",
              "oauth_identity_failed": "Google 계정 확인에 실패했어요. 연결 오류 코드: LOGIN-IDENTITY. 운영자에게 이 코드를 알려 주세요.",
              "oauth_permissions_failed": "Classroom 읽기 권한이 모두 허용되지 않았어요. 다시 연결할 때 요청한 수업·과제·공지·자료 읽기 권한을 모두 허용해 주세요. 연결 오류 코드: LOGIN-PERMISSIONS.",
              "oauth_storage_failed": "로그인 정보를 저장하지 못했어요. 연결 오류 코드: LOGIN-STORAGE. 운영자가 데이터베이스 연결과 암호화 설정을 확인해야 합니다.",
              "oauth_session_failed": "로그인 세션을 만들지 못했어요. 연결 오류 코드: LOGIN-SESSION. 운영자에게 이 코드를 알려 주세요.",
              "state_expired": "로그인 시간이 지났거나 이 브라우저에서 시작한 연결이 아니에요. 다시 시작해 주세요."}
    notice = f'<p class="notice">{errors[error]}</p>' if error in errors else ""
    action = '<p class="action-guide" id="login-guide">아래 버튼을 눌러 시작하세요.</p><a class="primary start-action" id="start-login" href="/auth/google" aria-describedby="login-guide"><span>Google로 시작하기</span><span aria-hidden="true">→</span></a>' if configured else '<p class="notice">로그인 연결을 준비 중이에요.</p>'
    privacy_url = html.escape(public_origin.rstrip("/") + "/privacy", quote=True)
    return page("모아", f'''<section class="welcome public-welcome">
    <h1>모아</h1><p class="welcome-title">내 과제와 신청 기한,<br>한곳에서 확인하세요.</p>
    <p class="service-purpose">Google Classroom의 과제·공지와 대회 신청 기한을 가까운 순서로 모아 보여 줍니다.</p>
    <section class="public-connection" aria-label="시작하기">
    <ol class="connect-steps" aria-label="연결 순서"><li aria-current="step"><span>1</span>학교 계정 로그인</li><li><span>2</span>읽기 권한 허용</li><li><span>3</span>수업 선택</li></ol>
    {notice}{action}
    <p class="permission-guide">다음 Google 화면에서 <strong>학교 계정</strong>을 선택하고<br>요청한 <strong>Classroom 읽기 권한을 모두 허용</strong>해 주세요.</p>
    <a class="dashboard-link" href="/app">이미 연결했다면 내 대시보드</a>
    </section>
    <div class="public-features">
      <section><h2>▤ 과제 마감</h2><p>해야 할 일을 가까운 기한부터.</p></section>
      <section><h2>♧ 대회·신청</h2><p>참여하고 싶은 활동의 신청일까지.</p></section>
      <section><h2>▦ 원문 확인</h2><p>본문을 펼쳐 보고 Classroom에서 확인.</p></section>
    </div>
    <p class="small">내 계정의 수업만 표시합니다. 게시물을 수정하거나 대신 제출하지 않습니다. AI 정리는 선택할 수 있으며 날짜는 원문에서 확인해 주세요.</p>
    <footer class="public-footer"><a href="{privacy_url}">모아 개인정보처리방침</a><a href="mailto:{SUPPORT_EMAIL}">문의: {SUPPORT_EMAIL}</a></footer>
    </section>''', description="모아는 Google Classroom 과제·공지·자료와 대회·활동 신청 기한을 한곳에 모아 확인하는 학생용 학습 관리 서비스입니다.")


def setup(user, csrf, selected, has_drive, ai_enabled):
    has_drive = False
    ai_option = ('<label class="ai-choice"><input id="auto-analyze" type="checkbox" checked>'
                 '<span>새 공지 AI 정리<small>본문·기존 PDF 텍스트를 BAZE로 보내는 데 동의합니다.</small></span></label>'
                 if ai_enabled else '')
    previous_link = '<a class="dashboard-link" href="/app">이미 불러온 과제 보기</a>' if selected else ''
    return page("수업 연결", f'''<section class="setup">
    <ol class="connect-steps" aria-label="연결 순서"><li class="step-done"><span>✓</span>로그인</li><li class="step-done"><span>✓</span>권한 허용</li><li aria-current="step"><span>3</span>수업 선택</li></ol>
    <h1>수업을 선택해 주세요.</h1>
    <p>체크한 수업의 과제와 공지를 가져옵니다.</p>
    <div id="account-message" class="notice" role="status" hidden></div><div class="choose-toolbar"><button id="select-all">전체 선택</button><button id="select-none">선택 해제</button></div>
    <div id="course-options" class="course-options"><p>수업을 불러오는 중…</p></div>
    {ai_option}
    <div class="setup-actions"><p id="selection-hint" class="action-guide" aria-live="polite">수업 선택 후 아래 버튼을 눌러 주세요.</p><button class="primary start-action" id="sync-courses" aria-describedby="selection-hint" disabled>수업을 먼저 선택해 주세요</button></div>
    <div id="job-progress" class="job-progress" hidden role="status"><span class="spinner"></span><span id="job-stage">연결 준비 중</span></div>
    {previous_link}
    <details class="connection-details"><summary>연결·AI 안내</summary><p>기존 분석은 재사용하고 한 게시물의 여러 할 일은 나누어 표시합니다. 새 PDF는 자동으로 읽지 않으니 첨부는 원문에서 확인해 주세요. AI 분석은 서비스 잔액이 2,000크레딧 미만이면 멈춥니다. 내 수업과 개인 기록만 표시합니다.</p></details>
    <button id="logout" class="text-button">로그아웃</button></section>''',
    {"csrf": csrf, "selected": selected, "aiEnabled": ai_enabled, "hasDrive": has_drive, "page": "setup"})


def privacy():
    return page("모아 개인정보처리방침", f'''<article class="policy">
    <h1>모아 개인정보처리방침</h1><p class="policy-date">시행일: 2026년 11월 7일 · 최종 수정일: 2026년 11월 8일</p>
    <p>모아는 Google Classroom의 과제·공지·자료와 선택 활동의 신청 기한을 모아 보는 학습 관리 서비스입니다.
    이 방침은 모아 웹서비스에서 Google 계정을 연결할 때 접근하는 정보, 이용 목적, 외부 서비스 처리, 보관과 삭제 방법을 설명합니다.</p>
    <h2>1. 운영 및 문의</h2><p>운영 주체는 모아 서비스 운영자입니다. 개인정보 열람·정정·삭제 및 서비스 문의는
    <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>로 보내 주세요. 확인 과정에서는 필요한 최소한의 계정 확인 정보를 요청하며 Google 비밀번호나 인증 토큰을 요청하지 않습니다.</p>
    <h2>2. 접근·수집하는 정보</h2><ul>
    <li>Google 로그인: Google 계정 식별자, 이름, 이메일, 로그인 확인과 API 연결 유지에 필요한 OAuth 인증 토큰.</li>
    <li>Classroom: 본인이 접근할 수 있는 수업 목록과 선택한 수업의 과제·공지·자료 게시물, 제목·본문·등록 기한·게시 시각·게시물 및 첨부 식별정보·원문 링크와 API가 제공하는 게시물 메타데이터. 게시물 본문에 다른 사람의 이름 등이 포함될 수 있습니다.</li>
    <li>기존 PDF 자료: 개발 중 사용자가 별도로 허용하여 이미 읽은 첨부 PDF와 추출한 텍스트는 보관할 수 있습니다. 현재 공개 웹 로그인에서는 Drive 권한을 요청하지 않으며, 새 PDF를 자동으로 다운로드하지 않습니다.</li>
    <li>개인 기록: 완료 표시, 관심 활동, 메모, 사용자가 입력한 기한, 수업 선택과 작업 진행 정보.</li>
    <li>연결 유지와 운영: 로그인 세션, 임시 OAuth 연결 상태, 고정된 로그인 단계·결과별 횟수와 마지막 발생 시각. 진단 집계에는 계정 이름·이메일·인증 코드·토큰을 저장하지 않습니다.</li></ul>
    <h2>3. 이용 목적과 선택 권한</h2><p>이 정보는 본인 확인, 수업 선택과 수집, 과제·활동 및 신청 기한 정리, 원문 확인, 개인 기록 저장, 연결 유지와 오류 확인에 사용합니다.
    각 사용자는 자신의 Google 계정으로 접근할 수 있는 수업과 자신의 개인 기록을 확인합니다. Classroom 게시물을 변경하거나 과제를 대신 제출하는 데 사용하지 않습니다.
    AI 정리는 선택 기능입니다. 기존 PDF 텍스트가 있으면 동의한 분석에 함께 사용합니다. Google에서 권한을 취소하면 해당 권한이 필요한 기능을 사용할 수 없습니다.</p>
    <h2>4. 처리에 사용하는 외부 서비스</h2><ul>
    <li>Google: 계정 인증과 사용자가 허용한 Classroom API 조회를 제공합니다. 공개 웹서비스는 Drive API 다운로드를 실행하지 않습니다.</li>
    <li>Render: 웹서버를 실행하며 요청 처리에 필요한 계정·수업 정보와 기존에 저장된 첨부 텍스트를 처리합니다.</li>
    <li>Neon: 계정 정보, 암호화된 Google 인증 토큰, 수집한 게시물, 개인 기록 및 분석 캐시를 비공개 데이터베이스에 저장합니다.</li>
    <li>BAZE: 운영자가 AI 기능을 활성화하고 사용자가 AI 정리 실행에 동의한 경우, 분석 대상 게시물의 제목·본문·시각·기한·식별정보,
    추출한 PDF 텍스트 및 관련 후속·이전 안내 문맥을 전달해 분석 응답을 받습니다. Google 인증 토큰과 개인 메모를 분석 입력으로 보내지 않습니다.</li></ul>
    <p>외부 서비스는 위 기능을 처리하기 위해 사용하며, 각 공급자의 처리·보관에는 해당 서비스의 정책과 계약이 적용됩니다.
    로그인, 홈페이지 열기와 일반 과제 목록 조회는 새로운 AI 생성 요청을 실행하지 않습니다.</p>
    <h2>5. Google 데이터의 제한적 사용</h2><p>모아는 Google API에서 받은 정보를 위 사용자용 기능을 제공하는 데 사용합니다.
    Google Workspace API에서 받은 정보는 일반화된 AI·머신러닝 모델의 개발·개선·학습에 사용하지 않습니다. AI 기능은 사용자가 선택한 자료를 요청 시점에 분석하는 용도로 사용합니다.
    Google 사용자 데이터를 판매하거나 광고 타기팅, 데이터 중개, 신용 평가에 사용하지 않습니다.</p>
    <p>Google API를 통해 받은 정보의 사용과 다른 앱으로의 전송에는 제한적 사용 요건을 포함한
    <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>를 따릅니다.</p>
    <h2>6. 보관 기간과 삭제</h2><p>계정 연결 정보, 수집본과 개인 기록은 연결된 계정의 기능을 제공하는 동안 보관합니다.
    동기화에서 관측한 등록 기한·본문 변경 내역은 계정별 수집본 안에 최근 100건까지 보관하며, 다른 계정에 공유하지 않습니다.
    로그인 세션은 최대 7일, 로그인 진행을 위한 임시 연결 상태는 최대 10분 동안 유효합니다. 만료된 상태는 이후 정리 과정에서 제거합니다.</p>
    <p>대시보드에서 <strong>연결 해제·내 데이터 삭제</strong>를 실행하면 Google 연결을 취소하고 운영 중인 데이터베이스에서 해당 계정의 인증정보·수집본·개인 기록·세션·작업 기록을 삭제하며 서버의 해당 계정 첨부 캐시도 제거합니다.
    진행 중인 수집·분석 작업이 있으면 작업이 끝난 뒤 삭제할 수 있습니다. Google 계정의
    <a href="https://myaccount.google.com/connections">서드 파티 연결 관리</a>에서도 권한을 취소할 수 있습니다. Google에서 권한을 취소하는 것과 모아에 저장된 기록을 삭제하는 것은 별도 절차입니다.</p>
    <p>동일한 게시물을 중복 분석하지 않도록 저장한 공통 분석 캐시에는 과제·기한·조건, 근거로 인용한 공지 문구와 게시물 식별정보가 포함될 수 있습니다.
    공통 캐시는 계정 삭제 후에도 남을 수 있으며, 해당 게시물에 접근할 수 있는 계정의 분석 재사용에만 사용합니다.
    관련 캐시의 삭제도 원하면 위 문의 이메일로 게시물 원문 링크와 함께 요청해 주세요. 운영자가 요청 대상과 접근 권한을 확인해 처리합니다.
    외부 공급자에게 이미 전달된 데이터의 보관·삭제에는 각 공급자의 정책과 계약도 적용됩니다.</p>
    <h2>7. 정보 보호</h2><p>공개 웹 연결은 HTTPS를 사용하고 데이터베이스 연결은 TLS로 보호합니다. Google 인증 토큰은 서버의 고정 키로 암호화하여 저장하고 브라우저에 전달하지 않습니다.
    개인 기록과 수집본은 서버에서 계정별 접근 권한을 확인합니다. 로그인에는 임시 연결 상태와 브라우저 연결 확인을 사용하고, 개인 기록 변경에는 요청 위조 방지 검사를 적용합니다.
    인증 코드·토큰·비밀 키를 애플리케이션 로그에 출력하지 않도록 처리합니다.</p>
    <h2>8. 쿠키 및 방침 변경</h2><p>로그인 유지와 Google 연결 확인을 위한 필수 쿠키를 사용합니다. 공개 웹서비스에는 광고용 추적 또는 방문 분석 스크립트를 포함하지 않습니다.
    처리 방식이 바뀌면 이 페이지의 내용과 최종 수정일을 갱신합니다. 문의 및 권리 행사 요청은 <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>로 보내 주세요.</p>
    <p><a href="/">모아 홈페이지로 돌아가기</a></p></article>''', description="모아의 Google 계정·Classroom·첨부 PDF 정보 이용, 외부 서비스 처리, 보관 기간과 삭제 방법을 안내합니다.")
