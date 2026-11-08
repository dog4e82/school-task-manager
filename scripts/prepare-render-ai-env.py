"""Prepare an ignored Render AI import file without printing secret values."""
import json
import sys
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import Client, BazeError


def main():
    values = dotenv_values(ROOT / '.env', encoding='utf-8-sig')
    base = (values.get('BAZE_BASE_URL') or '').strip()
    key = (values.get('BAZE_API_KEY') or '').strip()
    if not base or not key:
        raise ValueError('.env의 BAZE 설정을 먼저 확인하세요. 키를 채팅에 보내지 마세요.')
    if any('\n' in value or '\r' in value for value in (base, key)):
        raise ValueError('줄바꿈이 포함된 설정은 사용할 수 없습니다.')
    Client(base, key)
    settings = {'BAZE_BASE_URL': base, 'BAZE_API_KEY': key, 'WEB_AI_ENABLED': 'true'}
    output = ROOT / '.local/render-ai.env'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(name+'='+json.dumps(value)+'\n' for name, value in settings.items()), encoding='utf-8')
    print('.local/render-ai.env를 생성했습니다. Render Environment 가져오기에만 사용하세요.')
    print('실제 AI 호출은 실행하지 않았습니다. 키와 파일 내용을 채팅·Git에 올리지 마세요.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, BazeError) as error:
        print(str(error))
        raise SystemExit(1)
