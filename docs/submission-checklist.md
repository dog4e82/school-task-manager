# 모아 제출·시연 확인표

## 제출할 주소

- 서비스 소개: https://info.moa-classroom.dynv6.net
- 실제 앱: https://app.moa-classroom.dynv6.net
- 개인정보처리방침: https://info.moa-classroom.dynv6.net/privacy

소개·정책은 무료 Static Site로 제공한다. 앱의 무료 Web Service는 미사용 후 첫 접속이 느릴 수 있다. 소개 사이트와 앱 서버의 동작은 구분해서 확인한다.

## 현재 상태를 설명할 문구

모아는 Google Classroom의 과제·공지·수업 자료를 모아 제출 및 활동 신청 기한을 확인하는 웹서비스입니다. 서비스 배포와 개발자 학교 계정의 로그인·수업 수집을 확인했습니다. 운영자는 Google 브랜딩 게시와 서버 AI 활성화를 완료했다고 확인했습니다. 데이터 접근 검증은 완료 전이며, 모든 학교 계정의 이용을 보장하지 않습니다. 본인 계정의 PDF 연결과 전체 분석은 별도 실행·집계로 검증합니다.

## 시연 순서

1. 로그인하지 않은 브라우저에서 소개와 개인정보처리방침을 연다.
2. 본인의 Google 계정으로 연결하고 본인 수업을 선택한다.
3. 표시된 과제와 활동의 기한 및 상세 본문을 확인하고 원문을 연다.
4. 학교 게시물이나 타인의 개인정보가 포함된 영상은 공개하지 않는다. 필요한 경우 공개 허가된 시연용 수업으로 녹화한다.
5. 일반 사용자 계정으로 직접 시험하지 않은 기능은 완료했다고 적지 않는다. Google 심사 결과와 제출 마감은 별개이며, 제출 인정 여부는 담당 교사에게 확인한다.

## 운영자가 실행할 읽기 전용 점검

```powershell
uv run python scripts/export-public-site.py --check
uv run python scripts/check-public-web.py https://app.moa-classroom.dynv6.net
```

점검은 새 AI 생성이나 Classroom 수집을 실행하지 않는다. `passed`는 이 점검 환경에서의 결과이며 Google 인증 크롤러나 사용자 기기에서의 접속을 증명하지 않는다.

## Google 검증에서 남은 작업

- 브랜딩에 앱 이름 `모아`, 소개·개인정보처리방침의 정확한 주소를 저장한다. 공식 정책 주소는 `/privacy`다. 사용자는 주소를 `/priva`까지만 붙여 넣어서 발생한 404였다고 정정하고, 정확한 주소의 정상 작동을 확인했다.
- 기존 웹 OAuth의 이전 onrender.com 콜백·원본을 제거한 것을 확인한 뒤, 브랜딩의 이전 승인된 도메인도 정리한다. 현재 도메인은 `moa-classroom.dynv6.net`이다.
- 소유권 확인 이후 24시간 안내는 정보 반영을 위한 재시도 안내이며, 24시간 후 승인 보장이 아니다. 서비스 시연·제출 자체를 일괄적으로 금지하는 대기 시간도 아니다.
- 정확한 주소가 실제 사용자 환경에서도 열리는데 Google 검사만 실패한다면, 문제 보기에서 추가 검토 요청을 진행할 수 있다. 당일 승인을 보장하지 않는다.
- 브랜드 인증·게시 이후 필요한 데이터 접근 검증을 진행한다. 제한 권한 `drive.readonly`와 서버 처리에 대한 심사·보안 평가 요건은 별도로 남아 있다. 유료 평가를 자동 신청하지 않는다.

공식 절차: [브랜딩 검증과 추가 검토](https://support.google.com/cloud/answer/15549049), [제한된 권한 검증](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).
