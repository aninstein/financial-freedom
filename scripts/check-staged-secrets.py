#!/usr/bin/env python3
"""Check staged blobs without ever printing their content or secret values."""
import re
import subprocess
from pathlib import PurePosixPath


def git(*args):
    return subprocess.check_output(['git', *args])

bad = []
files = git('diff','--cached','--name-only','--diff-filter=ACMR','-z').decode().split('\0')
patterns = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b'),
    re.compile(r'''(?im)^\s*(?:AUTH_ENCRYPTION_KEY|AUTH_AUDIT_KEY|[A-Z0-9_]*(?:API_KEY|API_SECRET|ACCESS_TOKEN|PASSWORD))\s*=\s*["']?([A-Za-z0-9_+/.=-]{20,})'''),
    re.compile(r'''["']api_key["']\s*:\s*["']([A-Za-z0-9_+/.=-]{20,})["']'''),
]
for name in filter(None, files):
    path = PurePosixPath(name)
    if (path.name.startswith('.env') and path.name != '.env.example') or path.suffix in {'.pem','.key','.p12','.pfx','.sqlite3','.db'} or path.parts[0] in {'data','secrets','.runtime'}:
        bad.append((name,'private file'))
        continue
    raw = git('show', ':'+name)
    if b'\0' in raw or len(raw)>8_000_000:
        continue
    text = raw.decode('utf-8',errors='replace')
    for pattern in patterns:
        matches = list(pattern.finditer(text))
        if any(not any(marker in m.group(0).lower() for marker in ('your-', 'your_', 'example', 'placeholder', 'replace_', 'sk-xxx')) for m in matches):
            bad.append((name,'possible embedded credential'))
            break
if bad:
    for name, reason in bad:
        print(f'Blocked: {name} ({reason}); remove private values from the staged file.')
    raise SystemExit(1)
print(f'Staged secret check: {len(list(filter(None,files)))} files inspected, no detected credentials.')
