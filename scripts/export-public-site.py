"""Export only public information. Does not load secrets, account data or APIs."""

import argparse
import html
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web_pages import landing, privacy


def origin(value):
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError('Use an HTTPS origin without a path or credentials.')
    return value


def contents(app_origin, public_origin=''):
    home = landing(True, public_origin=public_origin)
    app_origin = html.escape(app_origin, quote=True)
    # Authentication stays at the application origin. No token is passed from
    # the public site, and the backend still creates its own bound OAuth flow.
    home = home.replace('href="/auth/google"', 'href="' + app_origin + '/auth/google"')
    home = home.replace('href="/app"', 'href="' + app_origin + '/app"')
    result = {}
    for path, body in [('index.html', home), ('privacy/index.html', privacy())]:
        body = body.replace('<script src="/assets/account.js" defer></script>', '')
        result[path] = body.encode('utf-8')
    result['assets/account.css'] = (ROOT / 'web/account.css').read_bytes()
    result['robots.txt'] = b'User-agent: *\nAllow: /\n'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-origin', type=origin, default='https://app.moa-classroom.dynv6.net')
    parser.add_argument('--public-origin', type=origin, default='https://info.moa-classroom.dynv6.net')
    parser.add_argument('--output', type=Path, default=ROOT / 'public-site')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for relative, body in contents(args.app_origin, args.public_origin or '').items():
        destination = args.output / relative
        if args.check:
            if not destination.exists() or destination.read_bytes() != body:
                raise SystemExit('Public site is outdated; rerun scripts/export-public-site.py with the intended origins.')
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
    print('Public site ' + ('matches source.' if args.check else 'exported. No account data, secrets or API calls used.'))


if __name__ == '__main__':
    main()
