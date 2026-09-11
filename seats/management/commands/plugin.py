from __future__ import annotations

import json
import re
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from seats.plugin_system import plugin_registry


PLUGIN_ID_RE = re.compile(r'^[a-z][a-z0-9_.-]{1,63}$')


class Command(BaseCommand):
    help = '管理与开发 FuckSeats Plugin API v1 插件'

    def add_arguments(self, parser):
        parser.add_argument(
            'operation',
            choices=('list', 'inspect', 'enable', 'disable', 'reload', 'uninstall', 'scaffold', 'dev'),
        )
        parser.add_argument('plugin_id', nargs='?')
        parser.add_argument('--interval', type=float, default=0.8)
        parser.add_argument('--clear-data', action='store_true')

    def handle(self, *args, **options):
        operation = options['operation']
        plugin_id = str(options.get('plugin_id') or '').strip()
        if operation == 'list':
            self.stdout.write(json.dumps(plugin_registry.list_plugins(detailed=True), ensure_ascii=False, indent=2))
            return
        if not plugin_id:
            raise CommandError('此操作需要 plugin_id')
        if operation == 'scaffold':
            self._scaffold(plugin_id)
            return
        if operation == 'inspect':
            rows = [row for row in plugin_registry.list_plugins(detailed=True) if row.get('id') == plugin_id]
            if not rows:
                raise CommandError(f'插件不存在：{plugin_id}')
            self.stdout.write(json.dumps(rows[0], ensure_ascii=False, indent=2))
            return
        if operation == 'enable':
            result = plugin_registry.enable_plugin(plugin_id)
        elif operation == 'disable':
            result = plugin_registry.disable_plugin(plugin_id)
        elif operation == 'reload':
            result = plugin_registry.reload(plugin_id)
        elif operation == 'uninstall':
            result = plugin_registry.uninstall_plugin(plugin_id, clear_data=options['clear_data'])
        elif operation == 'dev':
            self._watch(plugin_id, max(0.2, float(options['interval'])))
            return
        else:  # pragma: no cover
            raise CommandError('未知操作')
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))

    def _plugin_root(self):
        configured = list(getattr(settings, 'PLUGIN_DIRS', []) or [])
        return Path(configured[0] if configured else Path(settings.BASE_DIR) / 'plugins').expanduser().resolve()

    def _scaffold(self, plugin_id):
        if not PLUGIN_ID_RE.match(plugin_id):
            raise CommandError('plugin_id 必须以小写字母开头，且仅包含小写字母、数字、点、横线或下划线')
        target = self._plugin_root() / plugin_id
        if target.exists():
            raise CommandError(f'目标已存在：{target}')
        tests_dir = target / 'tests'
        tests_dir.mkdir(parents=True)
        (target / 'plugin.yaml').write_text(
            f'''id: {plugin_id}\nname: {plugin_id}\nversion: 0.1.0\napi_version: 1\nrequires:\n  app: ">=2.6,<3.0"\nentry: plugin.py\nauthor: 老三\nwebsite: www.577622.xyz\nlicense: GPL-3.0\ntrust_level: trusted\npermissions:\n  - plugin.runtime\n  - storage\n''',
            encoding='utf-8',
        )
        (target / 'plugin.py').write_text(
            f'''PLUGIN_META = {{"id": "{plugin_id}", "name": "{plugin_id}", "version": "0.1.0"}}\n\n\ndef hello(ctx):\n    count = ctx.storage.get("hello_count", 0) + 1\n    ctx.storage.set("hello_count", count)\n    return {{"message": "hello", "count": count}}\n\n\ndef register(registry):\n    registry.register_action("hello", hello, methods=("POST",))\n    registry.register_command("{plugin_id}.hello", title="{plugin_id}: Hello", action="hello")\n''',
            encoding='utf-8',
        )
        (tests_dir / '__init__.py').write_text('', encoding='utf-8')
        (tests_dir / 'test_plugin.py').write_text(
            '''from django.test import TestCase\n\n\nclass PluginSmokeTests(TestCase):\n    def test_placeholder(self):\n        self.assertTrue(True)\n''',
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS(f'插件脚手架已创建：{target}'))

    def _watch(self, plugin_id, interval):
        rows = [row for row in plugin_registry.list_plugins(detailed=True) if row.get('id') == plugin_id]
        if not rows:
            raise CommandError(f'插件不存在：{plugin_id}')
        root = Path(rows[0].get('manifest_path') or rows[0].get('path')).resolve().parent

        def snapshot():
            return {
                str(path): path.stat().st_mtime_ns
                for path in root.rglob('*')
                if path.is_file() and path.suffix.lower() in {'.py', '.json', '.yaml', '.yml', '.js'}
            }

        state = snapshot()
        self.stdout.write(f'监听 {root}，Ctrl+C 结束。')
        try:
            while True:
                time.sleep(interval)
                current = snapshot()
                if current == state:
                    continue
                state = current
                result = plugin_registry.reload(plugin_id)
                self.stdout.write(
                    f'[{time.strftime("%H:%M:%S")}] 已重载 {plugin_id}，耗时 {result.get("load_duration_ms", 0)}ms'
                )
        except KeyboardInterrupt:
            self.stdout.write('监听已结束。')
