#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export FINCH_UID="$(id -u)"

if [[ -f data/local-server.pid ]] && kill -0 "$(cat data/local-server.pid)" 2>/dev/null; then
  echo 'The old local server is running. Stop it before migrating its SQLite data.' >&2
  exit 1
fi
if python3 - "${APP_PORT:-8000}" <<'PY'
import socket, sys
with socket.socket() as probe:
    probe.settimeout(0.5)
    raise SystemExit(0 if probe.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)
PY
then
  if [[ -z "$(docker compose ps --status running -q web 2>/dev/null)" ]]; then
    echo "Port ${APP_PORT:-8000} is already in use. Stop the old server before starting Docker." >&2
    exit 1
  fi
fi

mkdir -p .runtime/secrets data
for name in mysql-password mysql-root-password; do
  if [[ ! -s ".runtime/secrets/$name" ]]; then
    python3 - "$name" <<'PY'
import pathlib, secrets, sys
path = pathlib.Path('.runtime/secrets') / sys.argv[1]
path.write_text(secrets.token_urlsafe(48) + '\n')
path.chmod(0o600)
PY
  fi
done
python3 - <<'PY'
import base64, pathlib, secrets
path = pathlib.Path('.env')
if not path.exists():
    path.write_text(pathlib.Path('.env.example').read_text())
content = path.read_text()
updates = {}
for name, value in {
    'AUTH_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    'AUTH_AUDIT_KEY': secrets.token_urlsafe(48),
}.items():
    if not any(line.startswith(name + '=') and line.split('=', 1)[1].strip() for line in content.splitlines()):
        updates[name] = value
if updates:
    lines = content.splitlines()
    for name, value in updates.items():
        positions = [index for index, line in enumerate(lines) if line.startswith(name + '=')]
        if positions:
            lines[positions[-1]] = f'{name}={value}'
        else:
            lines.append(f'{name}={value}')
    path.write_text('\n'.join(lines) + '\n')
path.chmod(0o600)
PY

python3 scripts/futu-host.py --ensure
docker compose config --quiet
docker compose build web
docker compose up -d --no-build --wait --remove-orphans web deerflow
printf 'finfreedom: http://127.0.0.1:%s\n' "${APP_PORT:-8000}"
