# Google 로그인 공개 전환

확인 기준: 2026-11-07. 웹 서버는 Render, 계정별 저장소는 Neon에서 운영한다. Google Cloud는 Google 로그인 및 Classroom API의 사용자 접근과 검증 설정을 관리한다. 서버를 Google Cloud로 이전할 필요는 없다.

## 현재 확인한 상태

- 공개 주소: https://moa-classroom.onrender.com
- 개인정보 안내: https://moa-classroom.onrender.com/privacy
- 승인된 웹 OAuth 콜백: https://moa-classroom.onrender.com/auth/callback
- 실제 Google 계정의 웹 로그인과 수업 선택 화면 진입은 확인했다.
- 사용자가 제공한 콘솔 상태 기준 Audience는 External(외부)이며 브랜딩 입력·저장을 마친 뒤 In production(프로덕션) 전환을 완료했다고 알렸다. Google 브랜드·데이터 접근 검증 승인은 확인 전이다.
- 웹 OAuth Client ID·Secret과 고정 암호화 키는 로그인에 성공한 현재 값을 유지한다.
- 사용자가 범위 추가를 진행한 뒤 제공한 검증 센터에는 데이터 접근이 미인증이며 민감·제한 범위 때문에 검증이 필요하다고 표시된다. 데이터 접근 검증 신청 전에 브랜딩을 인증·게시해야 한다는 안내가 있다. 브랜딩 인증·게시가 다음 단계이며, 전체 범위 목록의 일치는 별도 확인 전이다.
- 이후 브랜딩 검사에서는 홈페이지·정책 페이지 응답 실패, 도메인 소유권 미확인, 정책 링크·서비스 설명·이름 및 정책 내용 관련 문제가 보고됐다. 앱은 소개·정책 페이지를 로그인·DB 조회와 분리하고 명시적인 서비스 설명·정책 링크·브랜드명과 실제 처리 내역을 보완했다. 사용자는 보유한 도메인이 없다고 확인했다. 도메인 소유권과 무료 서버의 절전 시 접속 가능 여부는 해결 전이다.

## 콘솔에서 진행할 순서

1. 기존 프로젝트 `classroom-task-manager-513813`의 Google Auth platform → Audience(대상)를 연다.
2. Google 계정 사용자에게 공개하는 앱의 User type은 External(외부)인지 확인한다. 학교 조직 소유 프로젝트의 Internal은 해당 조직 사용자용이므로 구분한다.
3. Branding(브랜딩)에 실제 앱 이름, 운영자 연락처, 홈페이지와 개인정보 안내 URL을 등록한다. 연락처는 운영자가 실제로 확인할 수 있는 주소를 사용한다. 검증에 요구되는 도메인 소유권도 확인한다.
4. Data Access(데이터 액세스)에 아래 코드 기준 권한을 대조한다. 기본 로그인과 선택적인 PDF 읽기 권한을 모두 포함해 실제 요청 범위를 신고한다.
5. Audience에서 Publish app(앱 게시)으로 In production(프로덕션) 전환을 진행한다. 이 설정과 Google의 검증 승인은 별도 절차다.
6. Verification Center(검증 센터)에서 브랜드·범위 검증에 필요한 항목을 확인한다. 각 권한의 필요 이유와 실제 로그인→수업 선택→수집→기한 보기→연결 해제 과정을 보여 주는 시연 자료를 준비한다.
7. 검증 결과와 대상 설정을 확인한 뒤 테스트 사용자에 등록하지 않은 두 번째 계정으로 연결한다. 각 계정에는 그 계정이 접근할 수 있는 수업만 표시되는지 확인한다.

브랜딩의 앱 이름은 실제 서비스 표시명인 `모아`, 홈페이지와 개인정보 안내는 위 공개 URL을 사용한다. 지원 이메일과 개발자 연락처는 운영자가 실제로 읽을 수 있는 본인 계정을 선택·입력한다. 별도 이용약관 페이지는 현재 앱에 구현되어 있지 않으므로 존재하지 않는 `/terms` 주소를 입력하지 않는다.

정식 도메인 검증에서 요구하는 도메인 소유권과 DNS 확인은 별도로 해결해야 한다. Render의 기본 주소를 브랜딩에 저장했다는 사실만으로 소유권 검증이 완료된 것으로 처리하지 않는다. Google은 공유 도메인을 사용하는 서비스에 자체 소유 도메인 연결을 권고한다. [도메인 검증 안내](https://support.google.com/cloud/answer/13804266), [공유 호스팅 도메인 관련 정책](https://developers.google.com/identity/verification/authentication-policy-compliance).

앱을 게시해도 미승인 민감·제한 권한을 요청하면 경고와 일반적으로 총 100명 사용자 제한이 적용된다. 실제 콘솔 상태와 Google 검증 결과를 확인하기 전에는 무제한 공개가 완료됐다고 안내하지 않는다.

## 코드에서 요청하는 권한과 용도

| 범위 | 기능에 필요한 이유 |
| --- | --- |
| `openid` | Google ID 토큰을 검증하고 계정을 식별 |
| `https://www.googleapis.com/auth/userinfo.email` | 로그인한 계정의 이메일 확인 |
| `https://www.googleapis.com/auth/userinfo.profile` | 로그인한 계정의 이름 표시 |
| `https://www.googleapis.com/auth/classroom.courses.readonly` | 본인이 접근 가능한 수업 목록과 선택한 수업 정보 조회 |
| `https://www.googleapis.com/auth/classroom.student-submissions.me.readonly` | 본인에게 제공된 수업 과제와 제출 관련 정보 조회 |
| `https://www.googleapis.com/auth/classroom.announcements.readonly` | 선택한 수업의 공지 본문과 원문 링크 조회 |
| `https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly` | 선택한 수업의 자료 게시물 본문과 첨부 참조 조회 |
| `https://www.googleapis.com/auth/drive.readonly` | PDF 읽기를 추가로 허용한 사용자의 게시물 첨부 파일 다운로드 및 텍스트 추출 |

범위의 실제 분류는 콘솔 Data Access와 Google의 최신 범위 문서에서 확인한다. 현재 `drive.readonly`는 제한 범위다. 이 권한으로 접근한 데이터를 서버에 저장하거나 전송하는 공개 앱에는 보안 평가 요건이 추가된다. 예외 적용 여부와 비용·절차를 확인하기 전에 외부 평가를 신청하거나 유료 서비스를 만들지 않는다.

`drive.file`은 사용자가 앱에 선택·공유한 파일에 대한 좁은 권한이다. 현재의 Classroom 첨부 자동 다운로드를 유지한 채 범위 문자열만 바꾸는 대체 방식으로 취급하지 않는다. 해당 방식으로 전환한다면 파일 선택·연결 흐름을 별도로 설계하고 검증해야 한다.

학교 Google Workspace 관리자는 공개·검증된 앱에도 접근 제한을 적용할 수 있다. 우리 학교 전체 이용이 목표라면 관리자에게 기존 웹 OAuth 클라이언트와 필요한 범위의 허용을 요청하는 경로도 확인한다. 학교 관리자의 설정은 별도로 동의받아야 하며 이 문서 작성으로 변경되지 않는다.

## 무료 서버의 접속 실패와 정적 공개 페이지

Render 무료 Web Service는 미사용 시 절전 상태가 되며, 절전 중 `/robots.txt`는 Render가 접근 불허 응답을 반환한다. 이 경우 앱이 깨어 있을 때의 200 응답만으로 Google 크롤러 접근을 보장할 수 없다. 반복 호출이나 자동 재인증을 해결책으로 취급하지 않는다. [Render 무료 제한](https://render.com/docs/free).

`render.yaml`에는 공개 설명·정책 전용 무료 Static Site `moa-info`를 추가했다. 소스의 `public-site` 디렉터리 네 파일만 배포하며 Google 토큰·학교 게시물·환경변수는 필요하지 않다. 실제 서비스 생성과 공개 주소 확인은 별도 수행해야 한다. 기존 `moa-classroom` Web Service의 요금제·DB·인증정보는 유지한다.

```powershell
uv run python scripts/export-public-site.py
uv run python scripts/export-public-site.py --check
```

홈페이지와 정책은 `web_pages.py`와 `web/account.css`에서 생성한다. 해당 파일을 변경한 뒤에는 위 명령으로 정적 사본도 갱신한다. 로그인과 대시보드 링크는 `--app-origin https://실제앱주소`로 지정한다. 정적 홈페이지의 주소가 확정되면 `--public-origin https://실제공개주소`도 지정할 수 있다.

Render에서 기존 Blueprint `schclas`를 동기화하면 `moa-info` Static Site 추가 계획이 표시되어야 한다. 유료 인스턴스·디스크·DB 생성이 표시되면 적용하지 말고 구성부터 확인한다. 생성 후 실제 Static Site 주소의 `/`와 `/privacy`가 비로그인 상태로 즉시 응답하는지 검사한다.

도메인 소유권은 정적 호스팅과 별도다. 무료 DNS 제공 서비스의 주소를 사용한다면 A·TXT 수정 가능 여부, Public Suffix List상의 등록 경계, Render 연결 및 Google Search Console의 Domain 속성 검증을 각각 확인해야 한다. 무료 주소 발급이나 DNS 설정만으로 Google의 최종 검증 승인을 보장하지 않는다. 기존 `onrender.com` OAuth 콜백 도메인을 포함한 승인된 도메인 전체의 소유권 요건도 함께 확인한다. 현재는 새 주소나 OAuth 콜백을 변경하지 않았다.

소유권 확인이 완료된 뒤에는 Google이 안내한 대로 24시간 반영을 기다리고, 다른 지적 사항도 해결한 뒤 브랜딩을 재검증한다.

## 공식 문서

- [앱 대상과 게시 상태 관리](https://support.google.com/cloud/answer/15549945)
- [공개 상태·검증·학교 조직 정책의 관계](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
- [민감 범위 검증 준비](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [제한 범위 검증 준비](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [Drive 범위와 보안 평가 요건](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
