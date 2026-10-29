from __future__ import annotations

import io
import json
import asyncio
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import agent_extensions as ext
from app import deerflow_tools
from app.deerflow_worker import _config


def skill_zip(path: str = 'repo/.claude/skills/stock-research-executor/SKILL.md') -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr(path, '---\nname: stock-research-executor\ndescription: Research a stock using public evidence.\nallowed-tools: Task, mcp__reader__read\n---\n\n# Workflow\nUse evidence.\n')
        archive.writestr(str(Path(path).parent / 'references' / 'sources.md'), '# Sources\nPublic filings.\n')
    return output.getvalue()


class AgentExtensionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.patches = [
            patch.object(ext, 'EXTENSIONS_DIR', base),
            patch.object(ext, 'SKILLS_DIR', base / 'skills'),
            patch.object(ext, 'MCP_FILE', base / 'mcp.json'),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        deerflow_tools.unbind_run()
        self.tmp.cleanup()

    def test_zip_installs_one_skill_and_reference(self):
        installed = ext.install_skill_zip(skill_zip(), 'stock-research-executor')
        self.assertEqual(installed['name'], 'stock-research-executor')
        self.assertEqual(installed['requested_tools'], ['Task', 'mcp__reader__read'])
        self.assertEqual(ext.list_skills()[0]['name'], installed['name'])
        self.assertIn('Public filings', ext.read_skill(installed['name'], 'references/sources.md'))
        with self.assertRaises(ext.ExtensionError):
            ext.read_skill(installed['name'], '../mcp.json')

    def test_zip_rejects_traversal(self):
        with self.assertRaises(ext.ExtensionError):
            ext.install_skill_zip(skill_zip('../SKILL.md'))

    def test_mcp_config_is_private_and_read_only_by_default(self):
        ext.save_mcp_group({'mcpServers': {'research': {
            'command': 'npx', 'args': ['-y', '@example/research'],
            'env': {'API_TOKEN': 'sample-test-token'}}}})
        self.assertEqual(ext.MCP_FILE.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('sample-test-token', json.dumps(ext.list_mcp()))
        config = ext._load_mcp()
        config['research']['status'] = 'connected'
        config['research']['tools'] = [
            {'name': 'search', 'description': 'Search', 'inputSchema': {'type': 'object'}, 'readOnlyHint': True},
            {'name': 'write', 'description': 'Write', 'inputSchema': {'type': 'object'}, 'readOnlyHint': False},
        ]
        ext._save_mcp(config)
        self.assertIn('mcp__research__search', [x['function']['name'] for x in ext.mcp_tool_definitions()])
        deerflow_tools.register_extension_tools(ext.mcp_tool_definitions())
        self.assertTrue(hasattr(deerflow_tools, 'mcp__research__search'))
        ext.set_mcp_write_tools('research', True)
        self.assertIn('mcp__research__write', [x['function']['name'] for x in ext.mcp_tool_definitions()])

    def test_private_mcp_input_is_redacted_without_selecting_a_route(self):
        original = '添加 MCP：{"mcpServers":{"research":{"env":{"API_TOKEN":"secret"}}}}'
        safe, private = ext.redact_private_chat_input(original)
        self.assertEqual(private, original)
        self.assertIn('添加 MCP', safe)
        self.assertNotIn('secret', safe)
        self.assertEqual(ext.extract_mcp_config(private)['mcpServers']['research']['env']['API_TOKEN'], 'secret')
        plain, private = ext.redact_private_chat_input('请解释 mcpServers 是什么')
        self.assertEqual(plain, '请解释 mcpServers 是什么')
        self.assertIsNone(private)
        with self.assertRaises(ext.ExtensionError):
            ext.extract_mcp_config('请解释 mcpServers 是什么')

    def test_stdio_mcp_connects_and_calls_read_only_tool(self):
        ext.save_mcp_group({'mcpServers': {'fixture': {'command': 'python',
                            'args': ['tests/mcp_fixture.py']}}})
        status = asyncio.run(ext.probe_mcp('fixture'))
        self.assertEqual(status['status'], 'connected')
        self.assertEqual(status['tools'], ['lookup'])
        self.assertIn('mcp__fixture__lookup', [x['function']['name'] for x in ext.mcp_tool_definitions()])
        result = asyncio.run(ext.call_mcp_tool('mcp__fixture__lookup', {'symbol': 'ABC'}))
        self.assertIn('ABC: fixture', result['content'])

    def test_deerflow_tool_bridge_requires_activation(self):
        ext.install_skill_zip(skill_zip())
        class FakeTools:
            evidence = []
        state = deerflow_tools.RunState(FakeTools(), 'owner', 'run', frozenset({'activate_skill', 'read_skill_file'}), 3,
                                        skill_names=frozenset({'stock-research-executor'}))
        deerflow_tools.bind_run(state)
        denied = json.loads(deerflow_tools._execute('read_skill_file', {'name': 'stock-research-executor', 'path': 'references/sources.md'}))
        self.assertIn('error', denied)
        activated = json.loads(deerflow_tools._execute('activate_skill', {'name': 'stock-research-executor'}))
        self.assertIn('Workflow', activated['instructions'])
        read = json.loads(deerflow_tools._execute('read_skill_file', {'name': 'stock-research-executor', 'path': 'references/sources.md'}))
        self.assertIn('Public filings', read['content'])

    def test_deerflow_config_lists_selected_extension_tools(self):
        skill = ext.install_skill_zip(skill_zip())
        definitions = ext.skill_tool_definitions(True)
        deerflow_tools.register_extension_tools(definitions)
        allowed = frozenset(x['function']['name'] for x in definitions)
        env = {'DATA_DIR': self.tmp.name, 'MODEL_CONFIG_JSON':
               '[{"provider":"openai","model":"test","base_url":"http://127.0.0.1:9999/v1"}]',
               'PRIMARY_MODEL': 'test'}
        with patch.dict(os.environ, env):
            path, _ = _config({'question': '研究一只股票'}, allowed, [skill])
        try:
            import yaml
            config = yaml.safe_load(path.read_text())
        finally:
            path.unlink(missing_ok=True)
        names = {item['name'] for item in config['tools']}
        self.assertIn('activate_skill', names)
        self.assertIn('read_skill_file', names)
        self.assertIn('stock-research-executor', config['lead_prompt_overlay']['prepend'])


if __name__ == '__main__':
    unittest.main()
