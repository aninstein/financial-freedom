#!/usr/bin/env python3
"""Create private runtime ENV; optionally copy only model settings from a local project.
Never prints configuration values. Existing values are preserved.
"""
import argparse
import json
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--reference', type=Path, help='Reference project directory; only AI configuration is copied')
parser.add_argument('--sync-ai', action='store_true', help='Explicitly replace target AI settings from the given reference')
args = parser.parse_args()
target = root / '.env'
current = dict(dotenv_values(target)) if target.exists() else {}
updates = {}
if not current.get('AUTH_ENCRYPTION_KEY'):
    updates['AUTH_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
if not current.get('AUTH_AUDIT_KEY'):
    updates['AUTH_AUDIT_KEY'] = secrets.token_urlsafe(48)
for name, default in {'AUTH_LOGIN_VERIFICATION':'password', 'APP_ORIGIN':'http://127.0.0.1:8000', 'SESSION_COOKIE_SECURE':'false', 'SESSION_TTL_SECONDS':'28800', 'SESSION_IDLE_SECONDS':'1200'}.items():
    if name not in current:
        updates[name] = default
copied = False
if args.reference and (args.sync_ai or not current.get('MODEL_CONFIG_JSON')):
    ref = dict(dotenv_values(args.reference / '.env'))
    try:
        configs = json.loads(ref.get('MODEL_CONFIG_JSON') or '[]')
        if not isinstance(configs, list):
            raise ValueError()
    except (ValueError, TypeError):
        configs = []
    # Match the reference router: the official shortcut is prepended even when
    # MODEL_CONFIG_JSON also contains enabled fallback models.
    if ref.get('DEEPSEEK_OFFICIAL_API_KEY'):
        official_model = ref.get('DEEPSEEK_OFFICIAL_MODEL') or 'deepseek-flash'
        official = {'provider':'openai','model':official_model,
                    'base_url':ref.get('DEEPSEEK_OFFICIAL_BASE_URL') or 'https://api.deepseek.com/v1',
                    'api_key':ref['DEEPSEEK_OFFICIAL_API_KEY']}
        configs = [official, *[item for item in configs if not(isinstance(item,dict) and item.get('model')==official_model and item.get('provider','openai')=='openai')]]
    for index, config in enumerate(configs):
        if not isinstance(config, dict):
            continue
        if config.get('api_key'):
            name = f'AI_MODEL_API_KEY_{index+1}'
            updates[name] = str(config.pop('api_key'))
            config['api_key_env'] = name
        elif config.get('api_key_env') and ref.get(config['api_key_env']):
            name = f'AI_MODEL_API_KEY_{index+1}'
            updates[name] = str(ref[config['api_key_env']])
            config['api_key_env'] = name
    if configs:
        updates['MODEL_CONFIG_JSON'] = json.dumps(configs, ensure_ascii=False, separators=(',', ':'))
        names = [str(c.get('model', '')) for c in configs if isinstance(c,dict)]
        updates['PRIMARY_MODEL'] = ref.get('PRIMARY_MODEL') if ref.get('PRIMARY_MODEL') in names else names[0]
        for name in ['MODEL_TEMPERATURE','MODEL_TIMEOUT_SECONDS','AGENT_RUN_TIMEOUT_SECONDS','AGENT_MAX_TOOL_CALLS']:
            if ref.get(name) and name not in current:
                updates[name] = str(ref[name])
        copied = True
# Open atomically with owner-only permissions, including a preexisting ENV.
original = target.read_text() if target.exists() else '# Private local runtime configuration. Never commit this file.\n'
new = original.rstrip() + '\n' + ''.join(f'{name}={json.dumps(value, ensure_ascii=False)}\n' for name,value in updates.items())
temporary = root / '.env.local.tmp'
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write(new)
os.chmod(temporary, 0o600)
os.replace(temporary, target)
os.chmod(target, 0o600)
print('Private .env configured (mode 0600). AI configuration copied.' if copied else 'Private .env configured (mode 0600); existing AI settings preserved.')
