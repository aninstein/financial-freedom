#!/usr/bin/env python3
"""Create a private local .env and generate missing application keys."""
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

root = Path(__file__).resolve().parent.parent
target = root / '.env'
content = target.read_text() if target.exists() else (root / '.env.example').read_text()
updates = {
    'AUTH_ENCRYPTION_KEY': Fernet.generate_key().decode(),
    'AUTH_AUDIT_KEY': secrets.token_urlsafe(48),
}
lines = content.splitlines()
for name, value in updates.items():
    positions = [index for index, line in enumerate(lines) if line.startswith(name + '=')]
    if not positions or not lines[positions[-1]].split('=', 1)[1].strip():
        if positions:
            lines[positions[-1]] = f'{name}={value}'
        else:
            lines.append(f'{name}={value}')
private = root / '.env.local.tmp'
fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('\n'.join(lines) + '\n')
os.replace(private, target)
os.chmod(target, 0o600)
print('Private .env configured (mode 0600).')
