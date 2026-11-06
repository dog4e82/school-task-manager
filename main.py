"""BAZE 연결 테스트: 생성 요청은 analyze에서만 수행."""
import argparse
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from dotenv import load_dotenv

class BazeError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Client:
    def __init__(self, base, key):
        parts = urlsplit(base)
        if (parts.scheme != 'https' or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment):
            raise BazeError('BAZE_BASE_URL은 인증정보·쿼리가 없는 HTTPS URL이어야 합니다.')
        self.base, self.key = base.rstrip('/'), key
        self.opener = build_opener(NoRedirect())

    def request(self, path, payload=None):
        req = Request(self.base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + self.key,
                     'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='GET' if payload is None else 'POST')
        try:
            with self.opener.open(req, timeout=60) as response:
                result = json.load(response)
        except HTTPError as exc:
            hint = {401: '키가 유효하지 않거나 발급 배포와 URL이 다릅니다.',
                    403: '계정·모델 권한을 확인하세요.',
                    429: '요청 제한·크레딧 상태를 확인하세요.'}.get(exc.code, '요청 실패.')
            raise BazeError(f'HTTP {exc.code}: {hint} 자동 재시도하지 않았습니다.') from None
        except (URLError, TimeoutError, OSError):
            raise BazeError('네트워크 오류/시간 초과. 생성이 처리되었을 수도 있으므로 잔액을 조회하세요. 자동 재시도 없음.') from None
        except (ValueError, UnicodeError):
            raise BazeError('올바른 JSON 응답이 아닙니다.') from None
        if not isinstance(result, dict):
            raise BazeError('응답 형식이 예상과 다릅니다.')
        return result

    def models(self):
        result = self.request('/models/')
        data = result.get('data')
        if not isinstance(data, list) or not data or not all(
                isinstance(m, dict) and isinstance(m.get('id'), str) for m in data):
            raise BazeError('사용 가능한 모델 목록을 확인하지 못했습니다.')
        return result

    def emit(self, label, value):
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
        for secret in (self.key, json.dumps(self.key)[1:-1]):
            rendered = rendered.replace(secret, '[REDACTED]')
        print(f'{label}: {rendered}')

    def balance(self, label):
        result = self.request('/credits/')
        self.emit(label, {k: result[k] for k in
            ('monthly_allocated', 'purchased', 'org_granted', 'total') if k in result})
        return result

    def show_models(self, result):
        for m in result['data']:
            self.emit('모델', {k: m.get(k, '미제공') for k in ('id', 'type', 'pricing')})
        self.emit('환산 정보', {k: result[k] for k in
            ('exchange_rate', 'exchange_rate_date', 'credit_conversion_rate', 'vat_included') if k in result})
        print('단가는 API 제공 단위 그대로 표시합니다. 미제공 단가는 추정하지 않습니다.')

NOTICE = '과학 보고서를 제출하세요. 마감은 추후 공지합니다. 심화 문제 풀이는 선택 활동입니다. 참고 영상은 2026년 11월 10일 공개됩니다.'
PROMPT = '''학교 공지를 간결한 JSON으로 분석하라. items 배열 각 항목에 title,
 task_status(required/optional/reference/unknown), deadline_status(confirmed/unknown),
 deadline(명시된 마감만, 없으면 null), evidence(원문 인용)를 넣어라.
 과제 여부와 마감 확정 여부는 별도로 판단하라. 공개일을 마감으로 취급하지 말고,
 근거 없는 날짜나 제출 의무를 만들지 마라.'''

def analyze(client, model):
    catalog = client.models()
    selected = next((m for m in catalog['data'] if m['id'] == model), None)
    if not selected or selected.get('type') != 'llm' or 'codex' in model.lower():
        raise BazeError('조회된 llm 중 Chat Completions 지원 모델을 선택하세요. Codex 모델 제외.')
    client.emit('선택 모델', {'id': model, 'pricing': selected.get('pricing', '미제공')})
    before = client.balance('호출 전 잔액')
    print('고정 모의 공지를 1회 분석합니다. 실제 과금될 수 있습니다.')
    try:
        response = client.request('/chat/completions/', {
            'model': model, 'stream': False, 'max_tokens': 512,
            'messages': [{'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': NOTICE}]})
        client.emit('AI 분석 (검토용, 과제·마감 확정에 사용하지 않음)', response.get('choices', []))
        client.emit('사용량', response.get('usage', '미제공'))
        client.emit('차감 정보', response.get('billing', '미제공: 실제 차감량을 추정하지 않습니다.'))
    finally:
        try:
            after = client.balance('호출 후 잔액')
            try:
                delta = Decimal(str(before['total']['remaining'])) - Decimal(str(after['total']['remaining']))
                if delta.is_finite():
                    print(f'관측 잔액 감소량: {delta} (동시 사용·갱신·반영 지연 가능. 이번 호출의 확정 차감액이 아닙니다.)')
            except (KeyError, TypeError, InvalidOperation):
                print('잔액 차이 계산 불가: 수치 미제공.')
        except BazeError as exc:
            print(f'호출 후 잔액 확인 실패: {exc}', file=sys.stderr)
    print('출력이 비거나 잘려도 자동으로 다시 생성하지 않습니다.')

def main(argv=None):
    parser = argparse.ArgumentParser(description='BAZE 연결 테스트 (생성은 analyze만 수행)')
    sub = parser.add_subparsers(dest='command', required=True)
    for cmd in ('check', 'balance', 'models', 'pricing'):
        sub.add_parser(cmd)
    sub.add_parser('analyze', help='모의 공지 1회 분석 (과금 가능)').add_argument('--model', required=True)
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).with_name('.env'), override=False, encoding='utf-8-sig')
    try:
        base, key = (os.environ.get(k, '').strip() for k in ('BAZE_BASE_URL', 'BAZE_API_KEY'))
        if not base or not key:
            raise BazeError('BAZE_BASE_URL과 BAZE_API_KEY를 로컬 환경변수 또는 .env에 설정하세요.')
        client = Client(base, key)
        if args.command in ('check', 'models', 'pricing'):
            client.show_models(client.models())
        if args.command in ('check', 'balance'):
            client.balance('잔액')
        if args.command == 'analyze':
            analyze(client, args.model)
        print('명령 완료.')
        return 0
    except BazeError as exc:
        print(f'오류: {exc}', file=sys.stderr)
        return 1
    except (ValueError, UnicodeError):
        print('오류: 설정 또는 응답 형식 오류.', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
