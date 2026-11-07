"""Public introduction and authenticated course selection, without school sample data."""

import html
import json


def page(title, content, bootstrap=None):
    data = json.dumps(bootstrap or {}, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(title)} · 모아</title><link rel="stylesheet" href="/assets/account.css">
    <body><header><a class="logo" href="/">▦ 모아.</a><a href="/privacy">개인정보 안내</a></header><main>{content}</main>
    <script type="application/json" id="account-data">{data}</script><script src="/assets/account.js" defer></script></body></html>'''


def landing(configured, error=None):
    errors = {"google_denied": "Google 연결이 완료되지 않았어요. 계정과 읽기 권한을 확인하고 다시 연결하세요.",
              "oauth_failed": "로그인 연결을 확인하지 못했어요. 다시 시작해 주세요.",
              "oauth_token_failed": "Google 인증을 마무리하지 못했어요. 연결 오류 코드: LOGIN-TOKEN. 운영자가 서버의 Google 연결 설정과 통신 상태를 확인해야 합니다.",
              "oauth_identity_failed": "Google 계정 확인에 실패했어요. 연결 오류 코드: LOGIN-IDENTITY. 운영자에게 이 코드를 알려 주세요.",
              "oauth_permissions_failed": "Classroom 읽기 권한이 모두 허용되지 않았어요. 다시 연결할 때 요청한 수업·과제·공지·자료 읽기 권한을 모두 허용해 주세요. 연결 오류 코드: LOGIN-PERMISSIONS.",
              "oauth_storage_failed": "로그인 정보를 저장하지 못했어요. 연결 오류 코드: LOGIN-STORAGE. 운영자가 데이터베이스 연결과 암호화 설정을 확인해야 합니다.",
              "oauth_session_failed": "로그인 세션을 만들지 못했어요. 연결 오류 코드: LOGIN-SESSION. 운영자에게 이 코드를 알려 주세요.",
              "state_expired": "로그인 시간이 지났거나 이 브라우저에서 시작한 연결이 아니에요. 다시 시작해 주세요."}
    notice = f'<p class="notice">{errors[error]}</p>' if error in errors else ""
    action = '<a class="primary" href="/auth/google">Google로 Classroom 연결 <span>↗</span></a>' if configured else '<p class="notice">웹 연결을 준비하고 있습니다. 운영자의 연결 설정이 끝나면 로그인할 수 있어요.</p>'
    return page("나의 수업을 한곳에", f'''<section class="welcome"><div class="planner-symbol" aria-hidden="true">✓<span>▦</span></div>
    <h1>해야 할 과제부터,<br>도전하고 싶은 활동까지.</h1><p>내 Google Classroom을 연결하고<br>과제와 신청 기한을 가까운 순서로 확인하세요.</p>{notice}{action}
    <div class="feature-row"><span>▤ 과제 모아보기</span><span>♧ 대회·신청</span><span>▦ 가까운 마감</span></div>
    <p class="small">연결한 계정의 자료만 표시합니다. 과제와 공지를 수정하거나 대신 제출하지 않습니다.</p></section>''')


def setup(user, csrf, selected, has_drive, ai_enabled):
    return page("수업 연결", f'''<section class="setup"><span class="kicker">나의 학습 공간</span><h1>모아 볼 수업을 골라 주세요.</h1>
    <p>{html.escape(user['name'])}님의 계정에서 접근할 수 있는 수업을 불러옵니다.</p>
    <div id="account-message" class="notice" role="status" hidden></div><div class="choose-toolbar"><button id="select-all">전체 선택</button><button id="select-none">선택 해제</button></div>
    <div id="course-options" class="course-options"><p>수업을 불러오는 중…</p></div>
    <div class="pdf-option">{'<label><input id="include-pdf" type="checkbox"> 현재 안내의 첨부 PDF도 확인</label>' if has_drive else '<a href="/auth/google?pdf=1">첨부 PDF 읽기 권한도 연결하기 ↗</a>'}<small>기본 연결로 과제·공지 본문의 기한을 먼저 정리합니다.</small></div>
    <div class="setup-actions"><button class="primary" id="sync-courses" disabled>선택한 수업 연결</button><a href="/app">내 대시보드</a></div>
    <div id="job-progress" class="job-progress" hidden role="status"><span class="spinner"></span><span id="job-stage">연결 준비 중</span></div>
    <p class="small">공지의 AI 정리는 연결 후 별도로 선택합니다. 다른 사용자의 수업이나 개인 기록은 공유되지 않습니다.</p>
    <button id="logout" class="text-button">로그아웃</button></section>''',
    {"csrf": csrf, "selected": selected, "aiEnabled": ai_enabled, "hasDrive": has_drive, "page": "setup"})


def privacy():
    return page("개인정보 안내", '''<article class="policy"><h1>내 수업 데이터는 어떻게 사용되나요?</h1>
    <h2>연결하는 정보</h2><p>Google 계정 식별자·이름·이메일, 선택한 Classroom의 과제·공지·자료 본문과 등록 기한을 사용합니다. PDF 읽기를 추가로 허용하면 해당 게시물에 연결된 첨부 자료를 확인합니다.</p>
    <h2>사용 목적과 접근</h2><p>기한 정리와 개인 학습 관리에만 사용합니다. Google 인증 토큰은 서버에 암호화해 보관하며 브라우저에 전달하지 않습니다. 각 사용자는 자신의 Google 계정으로 조회한 자료와 개인 기록에만 접근할 수 있습니다.</p>
    <h2>선택하는 AI 정리</h2><p>사용자가 공지 AI 정리를 실행하면 선택된 안내의 제목·본문·이미 추출된 첨부 PDF 텍스트가 BAZE로 전송됩니다. 로그인이나 일반 목록 열기는 AI 생성 호출을 실행하지 않습니다. 동일한 게시물과 입력의 분석 결과는 다시 활용할 수 있으며, 타인의 수업 접근 권한을 얻는 데 사용하지 않습니다.</p>
    <h2>기록과 삭제</h2><p>완료 표시·관심 활동·메모는 로그인한 계정별로 저장합니다. 대시보드의 연결 해제·내 데이터 삭제를 누르면 Google 연결을 취소하고 해당 계정의 인증정보·수집본·개인 기록을 삭제합니다. 공통 분석 캐시는 접근 가능한 동일 공지를 정리하는 데만 재사용됩니다. 원문이 없는 공개 예제로 제공하거나 광고·판매에 사용하지 않습니다.</p>
    <h2>Google 데이터 사용</h2><p>Google API에서 받은 정보는 Google API Services User Data Policy의 제한적 사용 요건에 따라 사용하며, 일반 AI 모델의 학습을 위해 제공하지 않습니다. AI 제안과 날짜 추정은 원문과 교차 확인해야 합니다.</p>
    <p><a href="/">시작 화면으로 돌아가기</a></p></article>''')
