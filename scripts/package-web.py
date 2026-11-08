"""Package deployable source with an allowlist. Never include local account state."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
files = list(ROOT.glob("*.py"))
files += [ROOT / name for name in ("pyproject.toml", "uv.lock", "README.md", "Dockerfile", "render.yaml", ".dockerignore", ".gitignore", ".env.example", ".python-version")]
files += [p for directory in ("web", "docs") for p in (ROOT / directory).rglob("*") if p.is_file() and p.suffix in (".html", ".js", ".css", ".md")]
# Generated public pages have their own narrow allowlist; never package other
# local exports or any school examples alongside them.
files += [ROOT / 'public-site' / path for path in ('index.html', 'privacy/index.html', 'assets/account.css', 'robots.txt')
          if (ROOT / 'public-site' / path).is_file()]
files += list((ROOT / "tests").glob("test_*.py"))
files += [ROOT / "scripts" / name for name in ("package-web.py", "prepare-render-env.py", "prepare-render-ai-env.py", "check-postgres.py", "check-public-web.py", "export-public-site.py")]

# Compare actual local credentials in memory; never print their values.
private_values = set()
for name, value in dotenv_values(ROOT / ".env", encoding="utf-8-sig").items():
    if value and (name.upper() == "DATABASE_URL" or any(marker in name.upper() for marker in ("KEY", "SECRET", "TOKEN", "CLIENT_ID"))):
        private_values.add(value)


def collect_credentials(value):
    if isinstance(value, dict):
        for name, item in value.items():
            if name in {"client_id", "client_secret", "refresh_token", "access_token", "token", "id_token"} and isinstance(item, str):
                private_values.add(item)
            elif isinstance(item, (dict, list)):
                collect_credentials(item)
    elif isinstance(value, list):
        for item in value:
            collect_credentials(item)


for name in ("credentials.json", "credentials.web.json", "token.json"):
    candidate = ROOT / name
    if candidate.exists():
        collect_credentials(json.loads(candidate.read_text(encoding="utf-8-sig")))
token_key = ROOT / ".local" / "web" / "token-encryption.key"
if token_key.exists():
    private_values.add(token_key.read_text(encoding="ascii").strip())
for name, value in dotenv_values(ROOT / ".env.example", encoding="utf-8-sig").items():
    if value:
        raise SystemExit(".env.example에는 빈 값만 허용됩니다.")
contents = {}
for file in sorted(set(files)):
    relative = file.relative_to(ROOT).as_posix()
    if file.is_symlink() or ".local" in file.parts or file.name.startswith("credentials"):
        raise SystemExit("배포 제외 파일이 감지되었습니다.")
    content = file.read_bytes()
    if any(value.encode() in content for value in private_values if len(value) >= 8):
        raise SystemExit(f"배포 중단: 로컬 인증정보가 포함된 파일 {relative}")
    contents[relative] = content
output = ROOT / ".local" / "release"
output.mkdir(parents=True, exist_ok=True)
archive = output / "moa-web-source.zip"
manifest = []
with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
    for relative, content in contents.items():
        bundle.writestr(relative, content)
        manifest.append({"path": relative, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
(output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"배포 소스 {len(manifest)}개 파일: {archive}")
print("로컬 인증정보 대조 검사 통과. 환경변수·OAuth JSON·개인 수집본·SQLite·토큰·PDF 캐시 포함 없음.")
