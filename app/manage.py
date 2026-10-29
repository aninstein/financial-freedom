"""Local owner administration. Run: .venv/bin/python -m app.manage init-owner"""
from __future__ import annotations
import argparse
import getpass
import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)
from app import security as auth


def main():
    parser = argparse.ArgumentParser(description='finfreedom local identity management (interactive terminal only)')
    parser.add_argument('operation', choices=['init-owner', 'reset-password', 'reset-mfa', 'verify-audit'])
    args = parser.parse_args()
    auth.initialize()
    if args.operation == 'verify-audit':
        previous = ''
        with auth.connection() as c:
            rows = c.execute('SELECT * FROM audit ORDER BY id').fetchall()
        for row in rows:
            body = json.dumps([row['occurred_at'], row['actor'], row['action'], row['target'], previous], separators=(',', ':'), ensure_ascii=False)
            expected = hmac.new(auth.os.environ['AUTH_AUDIT_KEY'].encode(), body.encode(), hashlib.sha256).hexdigest()
            if row['prev_hash'] != previous or not hmac.compare_digest(expected, row['signature']):
                raise SystemExit('Audit integrity check failed.')
            previous = row['signature']
        print(f'Verified {len(rows)} audit entries. Tail deletion requires an external checkpoint to detect.')
        return
    username = input('Owner username: ').strip().casefold()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.@+-]{2,79}', username):
        raise SystemExit('Use 3–80 ASCII letters/numbers or _.@+- for username.')
    with auth.connection() as c:
        user = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        exists = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if args.operation == 'init-owner' and exists:
        raise SystemExit('An owner already exists. Public registration and additional owners are disabled.')
    if args.operation != 'init-owner' and not user:
        raise SystemExit('Owner not found.')
    if args.operation == 'reset-mfa':
        if input('Type the username again to reset MFA and revoke every session: ').strip().casefold() != username:
            raise SystemExit('Cancelled.')
        with auth.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('UPDATE users SET totp_secret=NULL,last_totp_step=-1,version=version+1 WHERE id=?', (user['id'],))
            c.execute('DELETE FROM recovery_codes WHERE user_id=?', (user['id'],))
            c.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            auth.audit(c, user['id'], 'local.mfa_reset')
        print('MFA reset; all sessions revoked. Bind an authenticator at the next login.')
        return
    password = getpass.getpass('New password (14–256 characters): ')
    try:
        auth.validate_password(password)
    except auth.HTTPException as exc:
        raise SystemExit(exc.detail['message']) from None
    if getpass.getpass('Repeat password: ') != password:
        raise SystemExit('Passwords differ.')
    encoded, now = auth.HASHER.hash(password), int(time.time())
    with auth.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        if args.operation == 'init-owner':
            # Check again under the database write lock.
            if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                raise SystemExit('An owner already exists.')
            uid = 'owner-' + secrets.token_hex(12)
            c.execute('INSERT INTO users(id,username,password_hash,created_at,password_changed_at) VALUES(?,?,?,?,?)', (uid, username, encoded, now, now))
            auth.audit(c, uid, 'local.owner_created')
        else:
            c.execute('UPDATE users SET password_hash=?,password_changed_at=?,version=version+1 WHERE id=?', (encoded, now, user['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            auth.audit(c, user['id'], 'local.password_reset')
    print('Owner credentials saved. Open the application to sign in and complete authenticator setup.')


if __name__ == '__main__':
    main()
