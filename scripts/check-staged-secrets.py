#!/usr/bin/env python3
"""Check staged blobs without ever printing their content or secret values."""
import re
import hashlib
import subprocess
import sys
from pathlib import PurePosixPath
from pathlib import Path


def git(*args):
    return subprocess.check_output(['git', *args])

bad = []
scan_all = '--all' in sys.argv[1:]
scan_worktree = '--worktree' in sys.argv[1:]
files = ((git('ls-files','-z') + git('ls-files','--others','--exclude-standard','-z')) if scan_worktree else
         git('ls-files','-z') if scan_all else
         git('diff','--cached','--name-only','--diff-filter=ACMR','-z')).decode().split('\0')
patterns = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b'),
    re.compile(r'''(?im)^\s*(?:AUTH_ENCRYPTION_KEY|AUTH_AUDIT_KEY|[A-Z0-9_]*(?:API_KEY|API_SECRET|ACCESS_TOKEN|PASSWORD))\s*=\s*["']?([A-Za-z0-9_+/.=-]{20,})'''),
    re.compile(r'''["']api_key["']\s*:\s*["']([A-Za-z0-9_+/.=-]{20,})["']'''),
    re.compile(r'/Us' + r'ers/[^\s"\']+'),
]
organization_markers = re.compile('|'.join((
    'byte' + 'dance', 'byte' + 'd', '字节' + '跳动',
    'volc' + 'engine',
)), re.IGNORECASE)
public_dependency_url = 'https://github.com/' + 'byte' + 'dance/deer-flow'
archives = {
    'vendor/deerflow/deerflow-extension-api-e9074b7.tar.gz': 'c483f602d46fcbe9e3f4297507e0a2b83e6faca6b0981bd10db729ffd189c167',
    'vendor/deerflow/deerflow-harness-e9074b7.tar.gz': 'fa134a76bdd1b5f6fbae5b4720319cebab38a978525349ac4b3544d134d11292',
}
for name in filter(None, files):
    path = PurePosixPath(name)
    if scan_worktree and not Path(name).is_file():
        continue
    raw = Path(name).read_bytes() if scan_worktree else git('show', ':'+name)
    if name in archives:
        if hashlib.sha256(raw).hexdigest() != archives[name]:
            bad.append((name, 'public dependency archive checksum mismatch'))
        continue
    if (path.name.startswith('.env') and path.name != '.env.example') or path.suffix in {'.pem','.key','.p12','.pfx','.sqlite3','.db','.zip','.gz'} or path.parts[0] in {'data','secrets','.runtime','artifacts'} or (path.parts[0] == 'vendor' and name != 'vendor/deerflow/provenance.json'):
        bad.append((name,'private file'))
        continue
    if b'\0' in raw or len(raw)>8_000_000:
        bad.append((name,'unscanned binary or oversized file'))
        continue
    text = raw.decode('utf-8',errors='replace')
    if organization_markers.search(name) or organization_markers.search(text.replace(public_dependency_url, '')):
        bad.append((name,'prohibited organization reference'))
        continue
    for pattern in patterns:
        matches = list(pattern.finditer(text))
        if any(not any(marker in m.group(0).lower() for marker in ('your-', 'your_', 'example', 'placeholder', 'replace_', 'sk-xxx')) for m in matches):
            bad.append((name,'possible embedded credential'))
            break
if bad:
    for name, reason in bad:
        print(f'Blocked: {name} ({reason}); remove private values from the staged file.')
    raise SystemExit(1)
print(f'{"Working tree" if scan_worktree else "Tracked" if scan_all else "Staged"} secret check: {len(list(filter(None,files)))} files inspected, no detected credentials.')
