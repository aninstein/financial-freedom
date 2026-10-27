"""Owner-managed Agent Skills and MCP connections.

All persistent extension state lives under DATA_DIR, outside the published source.
Installed skill files are data: this module never executes their scripts.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from contextlib import AsyncExitStack
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS_DIR = Path(os.getenv('AGENT_EXTENSIONS_DIR') or (Path(os.getenv('DATA_DIR', ROOT / 'data')) / 'agent-extensions')).resolve()
SKILLS_DIR = EXTENSIONS_DIR / 'skills'
MCP_FILE = EXTENSIONS_DIR / 'mcp.json'
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_UNPACKED_BYTES = 30 * 1024 * 1024
MAX_FILES = 300


class ExtensionError(ValueError):
    pass


def _prepare() -> None:
    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(EXTENSIONS_DIR, 0o700)
    os.chmod(SKILLS_DIR, 0o700)
    for name in ('npm-cache', 'uv-cache'):
        cache = EXTENSIONS_DIR / name
        cache.mkdir(mode=0o700, exist_ok=True)
        os.chmod(cache, 0o700)


def _read_skill(path: Path) -> dict:
    raw = path.read_text(encoding='utf-8')
    if len(raw) > 100_000 or not raw.startswith('---\n'):
        raise ExtensionError('SKILL.md 必须以 YAML 元数据开头，且小于 100 KB')
    parts = raw.split('---', 2)
    if len(parts) != 3:
        raise ExtensionError('SKILL.md 缺少元数据结束标记')
    metadata = yaml.safe_load(parts[1])
    if not isinstance(metadata, dict):
        raise ExtensionError('Skill 元数据格式无效')
    name = metadata.get('name')
    description = metadata.get('description')
    if not isinstance(name, str) or not SLUG.fullmatch(name) or len(name) > 64:
        raise ExtensionError('Skill name 必须是小写字母、数字和连字符')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ExtensionError('Skill description 缺失或过长')
    declared = metadata.get('allowed-tools') or []
    requested_tools = ([value.strip() for value in declared.split(',')] if isinstance(declared, str)
                       else declared if isinstance(declared, list) else [])
    requested_tools = [value for value in requested_tools if isinstance(value, str) and 0 < len(value) <= 100][:30]
    return {'name': name, 'description': description.strip(), 'license': str(metadata.get('license') or '')[:160],
            'requested_tools': requested_tools}


def list_skills() -> list[dict]:
    _prepare()
    found = []
    for directory in sorted(SKILLS_DIR.iterdir()):
        path = directory / 'SKILL.md'
        if not directory.is_dir() or directory.is_symlink() or not path.is_file():
            continue
        try:
            metadata = _read_skill(path)
            if metadata['name'] == directory.name:
                found.append({**metadata, 'path': str(directory), 'status': 'ready'})
        except (OSError, ExtensionError, yaml.YAMLError):
            continue
    return found


def read_skill(name: str, relative_path: str = 'SKILL.md') -> str:
    if not SLUG.fullmatch(name):
        raise ExtensionError('Skill 名称无效')
    base = SKILLS_DIR / name
    if not (base / 'SKILL.md').is_file():
        raise ExtensionError('Skill 未安装')
    requested = PurePosixPath(relative_path)
    if requested.is_absolute() or '..' in requested.parts or len(requested.parts) > 5:
        raise ExtensionError('Skill 文件路径无效')
    path = (base / requested).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file() or path.is_symlink():
        raise ExtensionError('Skill 文件不存在')
    if path.stat().st_size > 100_000 or path.suffix.lower() not in {'.md', '.txt', '.json', '.yaml', '.yml'}:
        raise ExtensionError('只允许读取小型文本参考文件')
    return path.read_text(encoding='utf-8')


def install_skill_zip(raw: bytes, requested_name: str | None = None) -> dict:
    if len(raw) > MAX_ZIP_BYTES:
        raise ExtensionError('压缩包最大 10 MB')
    _prepare()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ExtensionError('不是有效的 ZIP 压缩包') from exc
    with archive:
        members = archive.infolist()
        if len(members) > 5000:
            raise ExtensionError('仓库压缩包文件数超限')
        for item in members:
            part = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (part.is_absolute() or '..' in part.parts or '\\' in item.filename or
                    stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                raise ExtensionError('压缩包包含不安全路径或链接')
        candidates = [x for x in members if PurePosixPath(x.filename).name == 'SKILL.md']
        matches = []
        for item in candidates:
            try:
                with archive.open(item) as stream:
                    data = stream.read(100_001)
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / 'SKILL.md'
                    path.write_bytes(data)
                    metadata = _read_skill(path)
                if requested_name is None or metadata['name'] == requested_name:
                    matches.append((item, metadata))
            except (UnicodeError, ExtensionError, yaml.YAMLError):
                continue
        if len(matches) != 1:
            raise ExtensionError('未找到唯一匹配的 SKILL.md；请指定 skill 名称')
        selected, metadata = matches[0]
        prefix = PurePosixPath(selected.filename).parent
        selected_members = [item for item in members if not item.is_dir() and PurePosixPath(item.filename).is_relative_to(prefix)]
        if len(selected_members) > MAX_FILES or sum(item.file_size for item in selected_members) > MAX_UNPACKED_BYTES:
            raise ExtensionError('选中的 Skill 文件数或解压大小超限')
        if len({str(PurePosixPath(item.filename)) for item in selected_members}) != len(selected_members):
            raise ExtensionError('选中的 Skill 包含重复路径')
        dest = SKILLS_DIR / metadata['name']
        if dest.exists():
            raise ExtensionError('此 Skill 已安装；请先删除旧版本')
        with tempfile.TemporaryDirectory(dir=EXTENSIONS_DIR) as tmp:
            stage = Path(tmp) / metadata['name']
            stage.mkdir()
            for item in selected_members:
                part = PurePosixPath(item.filename)
                relative = part.relative_to(prefix)
                if not relative.parts or len(relative.parts) > 8:
                    continue
                target = stage.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o600)
            if _read_skill(stage / 'SKILL.md')['name'] != metadata['name']:
                raise ExtensionError('Skill 校验失败')
            stage.rename(dest)
    return {**metadata, 'path': str(dest), 'status': 'ready'}


async def install_skill_url(source: str, skill_name: str | None = None) -> dict:
    """Download a public GitHub repository archive; never run its installer."""
    value = source.strip().removeprefix('https://').removeprefix('http://')
    match = re.search(r'(?:^|\s)github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)', value)
    if not match:
        raise ExtensionError('目前支持公开 GitHub 仓库链接；其他来源请上传 ZIP')
    owner, repo = match.group(1), match.group(2).removesuffix('.git')
    url = f'https://codeload.github.com/{owner}/{repo}/zip/HEAD'
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            async with client.stream('GET', url) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_ZIP_BYTES:
                        raise ExtensionError('仓库压缩包超过 10 MB；请上传单个 Skill ZIP')
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ExtensionError(f'公开仓库下载失败：{type(exc).__name__}') from exc
    return install_skill_zip(b''.join(chunks), skill_name)


def delete_skill(name: str) -> None:
    if not SLUG.fullmatch(name):
        raise ExtensionError('Skill 名称无效')
    target = SKILLS_DIR / name
    if not target.is_dir() or target.is_symlink():
        raise ExtensionError('Skill 未安装')
    shutil.rmtree(target)


def skill_tool_definitions(installed: bool) -> list[dict]:
    if not installed:
        return []
    return [
        {'type': 'function', 'function': {
            'name': 'activate_skill',
            'description': '读取已安装 Skill 的完整说明；仅当当前问题与 Skill 描述相关时使用。',
            'parameters': {'type': 'object', 'properties': {'name': {'type': 'string'}},
                           'required': ['name'], 'additionalProperties': False}}},
        {'type': 'function', 'function': {
            'name': 'read_skill_file',
            'description': '读取已激活 Skill 目录里的文本参考文件。',
            'parameters': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'path': {'type': 'string'}},
                           'required': ['name', 'path'], 'additionalProperties': False}}},
    ]


def _load_mcp() -> dict:
    _prepare()
    if not MCP_FILE.exists():
        return {}
    try:
        raw = json.loads(MCP_FILE.read_text())
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        raise ExtensionError('MCP 配置文件格式无效') from None


def _save_mcp(configs: dict) -> None:
    _prepare()
    fd, name = tempfile.mkstemp(prefix='mcp-', suffix='.tmp', dir=EXTENSIONS_DIR)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(configs, stream, ensure_ascii=False, indent=2)
        os.replace(temp, MCP_FILE)
    finally:
        temp.unlink(missing_ok=True)
    MCP_FILE.chmod(0o600)


def _validate_mcp(name: str, item: dict) -> dict:
    if not SLUG.fullmatch(name) or len(name) > 64 or not isinstance(item, dict):
        raise ExtensionError('MCP 名称或配置无效')
    if 'url' in item:
        url = str(item['url'])
        parsed = urlparse(url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'}):
            raise ExtensionError('远程 MCP 必须使用 HTTPS；本机可使用 HTTP')
        if parsed.username or parsed.password or not parsed.hostname:
            raise ExtensionError('MCP URL 无效')
        headers = item.get('headers', {})
        if not isinstance(headers, dict) or len(headers) > 20 or any(
                not re.fullmatch(r'[A-Za-z0-9-]+', str(key)) or
                not isinstance(value, str) or len(value) > 4000
                for key, value in headers.items()):
            raise ExtensionError('MCP headers 格式无效')
        return {'url': url, 'headers': headers, 'type': 'http', 'enabled': True,
                'allow_write_tools': bool(item.get('allow_write_tools', False)), 'tools': []}
    command = item.get('command')
    args = item.get('args', [])
    env = item.get('env', {})
    if not isinstance(command, str) or not command or '/' in command or command not in {'npx', 'uvx', 'python', 'python3', 'node'}:
        raise ExtensionError('stdio MCP 仅支持 npx、uvx、python、python3 或 node 命令')
    if not isinstance(args, list) or len(args) > 30 or any(not isinstance(x, str) or len(x) > 500 for x in args):
        raise ExtensionError('MCP args 格式无效')
    if command == 'npx' and not {'-y', '--yes'} & set(args):
        raise ExtensionError('npx MCP 需要在 args 中加入 -y，以便非交互启动')
    if not isinstance(env, dict) or len(env) > 30 or any(not re.fullmatch(r'[A-Z][A-Z0-9_]*', str(k)) or not isinstance(v, str) or len(v) > 4000 for k, v in env.items()):
        raise ExtensionError('MCP env 格式无效')
    return {'command': command, 'args': args, 'env': env, 'type': 'stdio', 'enabled': True,
            'allow_write_tools': bool(item.get('allow_write_tools', False)), 'tools': []}


def save_mcp_group(raw: dict) -> list[str]:
    group = raw.get('mcpServers') if 'mcpServers' in raw else raw
    if not isinstance(group, dict) or not group or len(group) > 8:
        raise ExtensionError('请提供包含 1 至 8 个连接的 mcpServers 对象')
    configs = _load_mcp()
    names = []
    for name, item in group.items():
        if name == 'finch':
            raise ExtensionError('finch 是内置平台 MCP，不能覆盖')
        normalized = _validate_mcp(name, item)
        configs[name] = normalized
        names.append(name)
    _save_mcp(configs)
    return names


def list_mcp() -> list[dict]:
    rows = [{'name': 'finch', 'type': 'builtin', 'enabled': True, 'command': None,
             'url': None, 'allow_write_tools': True, 'tool_count': 3,
             'tools': ['catalog', 'read', 'write'], 'status': 'connected', 'managed': True}]
    for name, item in _load_mcp().items():
        if name == 'finch':
            continue
        rows.append({'name': name, 'type': item.get('type'), 'enabled': item.get('enabled', False),
                     'command': item.get('command'),
                     'url': (lambda parsed: f'{parsed.scheme}://{parsed.netloc}')(urlparse(item['url'])) if item.get('url') else None,
                     'allow_write_tools': item.get('allow_write_tools', False),
                     'tool_count': len(item.get('tools', [])), 'tools': [x.get('name') for x in item.get('tools', [])],
                     'status': item.get('status', 'not_checked')})
    return rows


def delete_mcp(name: str) -> None:
    configs = _load_mcp()
    if name not in configs:
        raise ExtensionError('MCP 连接不存在')
    del configs[name]
    _save_mcp(configs)


def set_mcp_write_tools(name: str, enabled: bool) -> dict:
    configs = _load_mcp()
    if name not in configs:
        raise ExtensionError('MCP 连接不存在')
    configs[name]['allow_write_tools'] = bool(enabled)
    _save_mcp(configs)
    return next(item for item in list_mcp() if item['name'] == name)


async def _mcp_session(item: dict, stack: AsyncExitStack):
    from mcp import ClientSession, StdioServerParameters
    if item['type'] == 'stdio':
        from mcp.client.stdio import stdio_client
        base_env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LANG') if key in os.environ}
        _prepare()
        base_env['npm_config_cache'] = str(EXTENSIONS_DIR / 'npm-cache')
        base_env['UV_CACHE_DIR'] = str(EXTENSIONS_DIR / 'uv-cache')
        command = sys.executable if item['command'] in {'python', 'python3'} else item['command']
        params = StdioServerParameters(command=command, args=item['args'], env={**base_env, **item.get('env', {})}, cwd=str(ROOT))
        errlog = stack.enter_context(open(os.devnull, 'w'))
        read, write = await stack.enter_async_context(stdio_client(params, errlog=errlog))
    else:
        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:
            raise ExtensionError('当前 MCP SDK 不支持 Streamable HTTP；请更新项目依赖') from exc
        read, write, _ = await stack.enter_async_context(streamablehttp_client(item['url'], headers=item.get('headers')))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session


async def probe_mcp(name: str) -> dict:
    if name == 'finch':
        return list_mcp()[0]
    configs = _load_mcp()
    if name not in configs:
        raise ExtensionError('MCP 连接不存在')
    item = configs[name]
    try:
        async with asyncio.timeout(25):
            async with AsyncExitStack() as stack:
                session = await _mcp_session(item, stack)
                result = await session.list_tools()
                tools = []
                for tool in result.tools[:60]:
                    data = tool.model_dump(mode='json', exclude_none=True)
                    tools.append({'name': data['name'], 'description': data.get('description', '')[:1000],
                                  'inputSchema': data.get('inputSchema', {'type': 'object'}),
                                  'readOnlyHint': bool((data.get('annotations') or {}).get('readOnlyHint'))})
        item['tools'], item['status'] = tools, 'connected'
    except Exception as exc:
        item['tools'], item['status'] = [], 'connection_failed:' + type(exc).__name__
    configs[name] = item
    _save_mcp(configs)
    return next(x for x in list_mcp() if x['name'] == name)


def mcp_tool_definitions() -> list[dict]:
    from app.platform_mcp import definitions as platform_definitions
    definitions = platform_definitions()
    for server, item in _load_mcp().items():
        if server == 'finch':
            continue
        if not item.get('enabled') or item.get('status') != 'connected':
            continue
        for tool in item.get('tools', []):
            if not tool.get('readOnlyHint') and not item.get('allow_write_tools'):
                continue
            name = f"mcp__{server}__{tool['name']}"
            if len(name) > 64 or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                continue
            definitions.append({'type': 'function', 'function': {
                'name': name, 'description': f"{server}: {tool.get('description', '')[:600]}",
                'parameters': tool.get('inputSchema', {'type': 'object'})}})
    return definitions[:43]


async def call_mcp_tool(composite_name: str, arguments: dict, owner_id: str | None = None) -> dict:
    if composite_name not in {x['function']['name'] for x in mcp_tool_definitions()}:
        raise ExtensionError('MCP 工具未启用')
    _, server, tool_name = composite_name.split('__', 2)
    if server == 'finch':
        if not owner_id:
            raise ExtensionError('内置平台 MCP 缺少账户身份')
        runtime_env = {key: os.environ[key] for key in
                       ('MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_DATABASE',
                        'MYSQL_PASSWORD_FILE', 'MYSQL_PASSWORD', 'DATA_DIR', 'CONTAINER_RUNTIME',
                        'FUTU_OPEND_HOST', 'FUTU_OPEND_PORT', 'FUTU_TRADE_ENABLED',
                        'FUTU_TRADE_SECURITY_FIRM', 'FUTU_REAL_ACCOUNT_IDS')
                       if key in os.environ}
        item = {'type': 'stdio', 'command': 'python', 'args': ['-m', 'app.platform_mcp_server'],
                'env': {**runtime_env, 'FINCH_MCP_OWNER_ID': owner_id}}
    else:
        item = _load_mcp()[server]
    async with asyncio.timeout(30):
        async with AsyncExitStack() as stack:
            session = await _mcp_session(item, stack)
            result = await session.call_tool(tool_name, arguments)
    data = result.model_dump(mode='json', exclude_none=True)
    content = json.dumps(data.get('content', []), ensure_ascii=False)[:16000]
    return {'server': server, 'tool': tool_name, 'isError': data.get('isError', False),
            'content': content, **({'error': content[:800]} if data.get('isError') else {})}


def parse_chat_action(question: str) -> tuple[str, object] | None:
    """Recognize an owner's direct installation request before sending it to a model."""
    text = question.strip()
    if 'mcpServers' in text:
        if not (text.startswith('{') or re.search(r'安装|添加|配置|接入|连接|install|add', text, re.I)):
            raise ExtensionError('MCP 配置请直接提交安装请求；配置内容不会发送给模型')
        decoder = json.JSONDecoder()
        for match in re.finditer(r'\{', text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
                if isinstance(value, dict) and 'mcpServers' in value:
                    return 'mcp', value
            except json.JSONDecodeError:
                continue
        raise ExtensionError('未找到有效的 mcpServers JSON；密钥不会发送给模型')
    if re.search(r'安装|添加|install', text, re.I) and 'github.com/' in text:
        source = re.search(r'(?:https?://)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', text)
        if source:
            named = re.search(r'(?:--skill\s+|skill\s+["“])([a-z0-9-]+)', text, re.I)
            return 'skill', {'source': source.group(0), 'name': named.group(1) if named else None}
    if 'npm_config_registry' in text:
        raise ExtensionError('安装请求缺少可识别的公开 Skill 仓库链接；配置内容不会发送给模型')
    return None


async def perform_chat_action(action: tuple[str, object]) -> tuple[str, str]:
    kind, data = action
    if kind == 'skill':
        result = await install_skill_url(data['source'], data.get('name'))
        dependencies = ('\n\n此 Skill 声明需要：' + '、'.join(result['requested_tools']) +
                        '。这些权限不会因安装而自动开启；请在设置页检查可用工具与 MCP 连接。') if result['requested_tools'] else ''
        return f"安装 Skill：{result['name']}", (f"已安装 **{result['name']}**，并显示在「数据与模型 → Skills」。\n\n"
                f"元数据描述：{result['description']}{dependencies}\n\n"
                "后续可直接要求我按此 Skill 的说明检查配置；对话会先读取完整 SKILL.md 和相关参考文件。Skill 内的脚本不会自动执行。")
    names = save_mcp_group(data)
    statuses = [await probe_mcp(name) for name in names]
    lines = [f"- **{item['name']}**：{'已连接' if item['status'] == 'connected' else '连接失败'}，发现 {item['tool_count']} 个工具。" for item in statuses]
    return '添加 MCP 连接', 'MCP 配置已保存到私有目录；凭据没有发送给模型或写入研究记录。\n' + '\n'.join(lines) + '\n可在「数据与模型 → MCP」查看状态；聊天只会调用标注为只读的工具。'
