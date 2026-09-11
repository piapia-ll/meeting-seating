from __future__ import annotations

import importlib.util
import inspect
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .actions import ActionRegistration, CommandRegistration, normalize_methods
from .context import PluginContext
from .errors import (
    PluginActionNotFoundError,
    PluginDisabledError,
    PluginMethodNotAllowedError,
    PluginNotFoundError,
)
from .events import HookRegistration, HookResult
from .lifecycle import LIFECYCLE_EVENTS, LifecycleRegistration, normalize_lifecycle_event
from .manifest import PLUGIN_API_VERSION, PluginCandidate, PluginManifest, discover_plugin_candidates, version_matches
from .permissions import PermissionSet
from .storage import MemoryStorageBackend, PluginCache, PluginStorageBundle


LOGGER = logging.getLogger(__name__)


@dataclass
class BasePluginRecord:
    manifest: PluginManifest
    module_name: str = ''
    module: Any = None
    path: str = ''
    manifest_path: str = ''
    enabled: bool = True
    installed: bool = False
    loaded_at: str = ''
    load_duration_ms: float = 0.0
    last_error: str = ''
    hooks: dict[str, int] = field(default_factory=dict)
    actions: dict[str, ActionRegistration] = field(default_factory=dict)
    commands: dict[str, CommandRegistration] = field(default_factory=dict)
    contributions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    lifecycle: dict[str, LifecycleRegistration] = field(default_factory=dict)
    ui_scripts: dict[str, Any] = field(default_factory=dict)
    workspace_scripts: dict[str, Any] = field(default_factory=dict)
    routes: dict[str, Any] = field(default_factory=dict)
    url_patterns: list[Any] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def plugin_id(self):
        return self.manifest.plugin_id

    @property
    def name(self):
        return self.manifest.name

    @property
    def version(self):
        return self.manifest.version


class BasePluginRegistry:
    runtime_name = 'core'

    def __init__(self, *, app_version='0.0.0', storage_backend=None, services=None):
        self.app_version = str(app_version or '0.0.0')
        self.api_version = PLUGIN_API_VERSION
        self.storage_backend = storage_backend or MemoryStorageBackend()
        self.services = dict(services or {})
        self._lock = threading.RLock()
        self._loaded = False
        self._loading = False
        self._current_plugin_id: str | None = None
        self._plugins: dict[str, BasePluginRecord] = {}
        self._hooks: dict[str, list[HookRegistration]] = {}
        self._load_errors: list[dict[str, str]] = []
        self._sequence = 0
        self._caches: dict[str, PluginCache] = {}
        self._app_ready = False
        self._app_ready_emitted = False

    @property
    def load_errors(self):
        return list(self._load_errors)

    def resolve_plugin_dirs(self):
        raise NotImplementedError

    def record_factory(self, manifest: PluginManifest, **kwargs):
        return BasePluginRecord(manifest=manifest, **kwargs)

    def reset_for_tests(self):
        with self._lock:
            self._loaded = False
            self._loading = False
            self._current_plugin_id = None
            self._plugins = {}
            self._hooks = {}
            self._load_errors = []
            self._sequence = 0
            self._caches = {}
            self._app_ready_emitted = False

    def mark_app_ready(self):
        self._app_ready = True
        if self._loaded and not self._app_ready_emitted:
            self._app_ready_emitted = True
            self.emit('app_ready')

    def _module_name_from_path(self, file_path: Path, plugin_id='plugin'):
        safe_name = str(plugin_id or file_path.stem).replace('-', '_').replace('.', '_')
        return f'fuckseats_{self.runtime_name}_plugins.{safe_name}_{abs(hash(str(file_path.resolve())))}'

    def _load_module(self, candidate: PluginCandidate, manifest_hint: PluginManifest | None):
        if candidate.entry_path is None:
            return '', None, {}
        if manifest_hint is not None and manifest_hint.trust_level == 'sandboxed':
            if candidate.entry_path.suffix == '.py':
                raise ValueError('sandboxed 扩展不得包含 Python 入口，请使用声明式 contributes')
        module_name = self._module_name_from_path(
            candidate.entry_path,
            manifest_hint.plugin_id if manifest_hint else candidate.entry_path.stem,
        )
        spec = importlib.util.spec_from_file_location(module_name, candidate.entry_path)
        if spec is None or spec.loader is None:
            raise RuntimeError('无法创建模块加载器')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module_meta = getattr(module, 'PLUGIN_META', {}) or {}
        if not isinstance(module_meta, dict):
            raise ValueError('PLUGIN_META 必须是 dict')
        return module_name, module, module_meta

    def _candidate_fallback_id(self, candidate):
        if candidate.entry_path is None:
            return candidate.root.name
        if candidate.entry_path.name in {'plugin.py', '__init__.py'}:
            return candidate.entry_path.parent.name
        return candidate.entry_path.stem

    def _build_manifest_hint(self, candidate):
        if not candidate.manifest_data:
            return None
        return PluginManifest.from_mapping(
            candidate.manifest_data,
            fallback_id=self._candidate_fallback_id(candidate),
            source='manifest',
        )

    def _register_candidate_record(self, candidate: PluginCandidate):
        started = time.perf_counter()
        manifest_hint = self._build_manifest_hint(candidate)
        module_name, module, module_meta = self._load_module(candidate, manifest_hint)
        # Manifest 是一等协议，显式字段覆盖兼容用的 PLUGIN_META。
        combined = {**module_meta, **candidate.manifest_data}
        source = 'manifest' if candidate.manifest_data else 'legacy'
        manifest = PluginManifest.from_mapping(
            combined,
            fallback_id=self._candidate_fallback_id(candidate),
            source=source,
        )
        manifest.validate_compatibility(self.app_version, self.api_version)
        if manifest.plugin_id in self._plugins:
            raise ValueError(f'插件 ID 冲突：{manifest.plugin_id}')

        enabled = bool(self.storage_backend.get(
            manifest.plugin_id,
            '__runtime__',
            f'{self.runtime_name}.enabled',
            True,
        ))
        installed = bool(self.storage_backend.get(
            manifest.plugin_id,
            '__runtime__',
            f'{self.runtime_name}.installed',
            False,
        ))
        record = self.record_factory(
            manifest,
            module_name=module_name,
            module=module,
            path=str(candidate.entry_path or candidate.root),
            manifest_path=str(candidate.manifest_path or ''),
            enabled=enabled,
            installed=installed,
            loaded_at=datetime.now(timezone.utc).isoformat(),
            load_duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        self._plugins[manifest.plugin_id] = record
        return record

    def _validate_dependencies(self):
        invalid: dict[str, str] = {}
        changed = True
        while changed:
            changed = False
            for record in self._plugins.values():
                if record.plugin_id in invalid:
                    continue
                for dependency_id, version_rule in record.manifest.dependencies.items():
                    dependency = self._plugins.get(dependency_id)
                    if dependency is None:
                        invalid[record.plugin_id] = f'{record.plugin_id} 缺少依赖插件：{dependency_id}'
                        changed = True
                        break
                    if dependency_id in invalid:
                        invalid[record.plugin_id] = f'{record.plugin_id} 的依赖插件不可用：{dependency_id}'
                        changed = True
                        break
                    if version_rule and not version_matches(dependency.version, version_rule):
                        invalid[record.plugin_id] = (
                            f'{record.plugin_id} 需要 {dependency_id} {version_rule}，当前为 {dependency.version}'
                        )
                        changed = True
                        break
        for plugin_id, message in invalid.items():
            record = self._plugins[plugin_id]
            record.enabled = False
            record.last_error = message
            self._load_errors.append({
                'path': record.manifest_path or record.path,
                'error': message,
            })
        return set(invalid)

    def _register_manifest_contributions(self, record: BasePluginRecord):
        contributes = record.manifest.contributes
        commands = contributes.get('commands') or []
        if isinstance(commands, dict):
            commands = [dict(value, id=key) for key, value in commands.items() if isinstance(value, dict)]
        for item in commands:
            if not isinstance(item, dict):
                continue
            command_id = str(item.get('id') or item.get('command') or '').strip()
            if not command_id:
                continue
            self.register_command(
                command_id,
                title=str(item.get('title') or item.get('label') or command_id),
                description=str(item.get('description') or ''),
                shortcut=str(item.get('shortcut') or ''),
                action=str(item.get('action') or ''),
                placements=item.get('placements') or ('command_palette',),
                permissions=item.get('permissions') or (),
                plugin_id=record.plugin_id,
            )

        for key, rows in contributes.items():
            if key == 'commands':
                continue
            if isinstance(rows, dict):
                rows = [rows]
            for item in rows or []:
                if not isinstance(item, dict):
                    continue
                slot = str(item.get('slot') or item.get('placement') or key).strip()
                self.register_contribution(slot, item, plugin_id=record.plugin_id)

    def _register_module(self, record: BasePluginRecord):
        self._current_plugin_id = record.plugin_id
        try:
            self._register_manifest_contributions(record)
            module = record.module
            if module is None:
                return
            register_fn = getattr(module, 'register', None)
            if callable(register_fn):
                register_fn(self)
            elif record.manifest.source == 'legacy':
                raise ValueError('插件缺少 register(registry) 函数')
            for event in LIFECYCLE_EVENTS:
                handler = getattr(module, event, None)
                if callable(handler) and event not in record.lifecycle:
                    self.register_lifecycle(event, handler, plugin_id=record.plugin_id)
        finally:
            self._current_plugin_id = None

    def _call_lifecycle(self, record, event, **extra):
        registration = record.lifecycle.get(event)
        if registration is None:
            return None
        ctx = self.create_context(record.plugin_id, lifecycle_event=event, **extra)
        return self._invoke_callable(registration.handler, ctx)

    def ensure_loaded(self):
        with self._lock:
            if self._loaded or self._loading:
                return
            self._loading = True
            try:
                candidates = discover_plugin_candidates(self.resolve_plugin_dirs())
                for candidate in candidates:
                    try:
                        self._register_candidate_record(candidate)
                    except Exception as exc:
                        path = candidate.manifest_path or candidate.entry_path or candidate.root
                        self._load_errors.append({'path': str(path), 'error': str(exc)})
                        LOGGER.warning('加载插件元数据失败: %s: %s', path, exc)

                invalid_dependencies = self._validate_dependencies()

                for record in list(self._plugins.values()):
                    if record.plugin_id in invalid_dependencies:
                        continue
                    try:
                        self._register_module(record)
                        if not record.installed:
                            self._call_lifecycle(record, 'on_install')
                            record.installed = True
                            self.storage_backend.set(
                                record.plugin_id, '__runtime__', f'{self.runtime_name}.installed', True,
                            )
                        self._call_lifecycle(record, 'on_load')
                        if record.enabled:
                            self._call_lifecycle(record, 'on_enable')
                    except Exception as exc:
                        record.enabled = False
                        record.last_error = str(exc)
                        self._load_errors.append({'path': record.path, 'error': str(exc)})
                        LOGGER.exception('注册插件失败: %s', record.plugin_id)
            finally:
                self._loading = False
                self._loaded = True
            if self._app_ready and not self._app_ready_emitted:
                self._app_ready_emitted = True
                self.emit('app_ready')

    def _current_record(self, plugin_id=None):
        pid = str(plugin_id or self._current_plugin_id or '').strip()
        if not pid:
            raise ValueError('需要 plugin_id 或在 register() 内部调用')
        record = self._plugins.get(pid)
        if record is None:
            raise PluginNotFoundError(f'插件不存在：{pid}')
        return record

    def get_storage_bundle(self, plugin_id: str):
        cache = self._caches.setdefault(plugin_id, PluginCache(plugin_id))
        return PluginStorageBundle.create(self.storage_backend, plugin_id, cache=cache)

    def create_context(self, plugin_id: str, **context):
        record = self._current_record(plugin_id)
        reserved = {'request', 'payload', 'classroom', 'user', 'services'}
        extra = {key: value for key, value in context.items() if key not in reserved}
        service_factories = dict(self.services)
        service_factories.update(context.get('services') or {})
        ctx = PluginContext(
            plugin_id=record.plugin_id,
            registry=self,
            plugin=record,
            request=context.get('request'),
            payload=context.get('payload') if isinstance(context.get('payload'), dict) else {},
            classroom=context.get('classroom'),
            user=context.get('user'),
            services={},
            extra=extra,
        )
        for name, factory in service_factories.items():
            service = factory(ctx) if callable(factory) else factory
            ctx.attach_service(name, service)
        return ctx

    def _invoke_callable(self, func: Callable[..., Any], context: PluginContext):
        signature = inspect.signature(func)
        if not signature.parameters:
            return func()
        if len(signature.parameters) == 1:
            parameter = next(iter(signature.parameters.values()))
            if parameter.name == 'request':
                return func(context.request)
            if parameter.name == 'payload':
                return func(context.payload)
            return func(context)
        values = context.to_dict()
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
            return func(**values)
        accepted = {key: value for key, value in values.items() if key in signature.parameters}
        return func(**accepted)

    def _invoke_timed(self, handler, context, stats):
        started = time.perf_counter()
        error = None
        try:
            return self._invoke_callable(handler, context)
        except Exception as exc:
            error = exc
            raise
        finally:
            stats.record((time.perf_counter() - started) * 1000, error=error)

    def require_permission(self, plugin_id, capability, *, request=None, classroom=None):
        record = self._current_record(plugin_id)
        permissions = PermissionSet.from_value(record.manifest.permissions)
        permissions.require(
            capability,
            plugin_id=plugin_id,
            legacy_trusted=record.manifest.source == 'legacy' and record.manifest.trust_level == 'trusted',
        )
        return True

    def register_lifecycle(self, event, handler, *, plugin_id=None):
        record = self._current_record(plugin_id)
        event_name = normalize_lifecycle_event(event)
        if not callable(handler):
            raise ValueError('生命周期 handler 必须可调用')
        record.lifecycle[event_name] = LifecycleRegistration(event_name, handler)

    def register_hook(self, event, handler, *, priority=0, kind='notification', plugin_id=None):
        record = self._current_record(plugin_id)
        if not callable(handler):
            raise ValueError('hook handler 必须是可调用对象')
        event_name = str(event or '').strip()
        if not event_name:
            raise ValueError('hook event 不能为空')
        kind_value = str(kind or 'notification').strip().lower()
        if kind_value not in {'notification', 'intervention'}:
            raise ValueError('hook kind 仅支持 notification 或 intervention')
        self._sequence += 1
        hook = HookRegistration(
            plugin_id=record.plugin_id,
            event=event_name,
            handler=handler,
            priority=int(priority or 0),
            kind=kind_value,
            sequence=self._sequence,
        )
        self._hooks.setdefault(event_name, []).append(hook)
        self._hooks[event_name].sort(key=lambda item: (-item.priority, item.sequence))
        record.hooks[event_name] = record.hooks.get(event_name, 0) + 1

    def hook(self, event, **options):
        def decorator(func):
            self.register_hook(event, func, **options)
            return func
        return decorator

    def register_action(
        self,
        action,
        handler,
        *,
        methods=('POST',),
        description='',
        permissions=(),
        auth_required=False,
        plugin_id=None,
    ):
        record = self._current_record(plugin_id)
        if not callable(handler):
            raise ValueError('action handler 必须是可调用对象')
        action_name = str(action or '').strip()
        if not action_name:
            raise ValueError('action 名称不能为空')
        if action_name in record.actions:
            raise ValueError(f'重复 action：{action_name}')
        record.actions[action_name] = ActionRegistration(
            name=action_name,
            handler=handler,
            methods=normalize_methods(methods),
            description=str(description or ''),
            permissions=tuple(str(item) for item in (permissions or ())),
            auth_required=bool(auth_required),
        )

    def action(self, name, **options):
        def decorator(func):
            self.register_action(name, func, **options)
            return func
        return decorator

    def register_command(
        self,
        command_id,
        *,
        title,
        handler=None,
        action='',
        description='',
        shortcut='',
        placements=('command_palette',),
        permissions=(),
        plugin_id=None,
    ):
        record = self._current_record(plugin_id)
        command_key = str(command_id or '').strip()
        if not command_key:
            raise ValueError('command id 不能为空')
        if handler is not None and not callable(handler):
            raise ValueError('command handler 必须可调用')
        if handler is None and not str(action or '').strip():
            # 声明式命令可以仅作导航/前端命令，由前端读取 contribution 处理。
            action = ''
        if command_key in record.commands:
            raise ValueError(f'重复 command：{command_key}')
        if isinstance(placements, str):
            placements = [placements]
        record.commands[command_key] = CommandRegistration(
            command_id=command_key,
            title=str(title or command_key),
            description=str(description or ''),
            shortcut=str(shortcut or ''),
            handler=handler,
            action=str(action or ''),
            placements=tuple(str(item) for item in (placements or ()) if str(item).strip()),
            permissions=tuple(str(item) for item in (permissions or ()) if str(item).strip()),
        )

    def command(self, command_id, **options):
        def decorator(func):
            self.register_command(command_id, handler=func, **options)
            return func
        return decorator

    def register_contribution(self, slot, contribution, *, plugin_id=None):
        record = self._current_record(plugin_id)
        slot_name = str(slot or '').strip()
        if not slot_name:
            raise ValueError('contribution slot 不能为空')
        if not isinstance(contribution, dict):
            raise ValueError('contribution 必须是 dict')
        row = dict(contribution)
        row.setdefault('id', f'{record.plugin_id}.{slot_name}.{len(record.contributions.get(slot_name, [])) + 1}')
        row['plugin_id'] = record.plugin_id
        row['slot'] = slot_name
        record.contributions.setdefault(slot_name, []).append(row)
        return row

    def contribute(self, slot, contribution=None, *, plugin_id=None, **props):
        payload = dict(contribution or {})
        payload.update(props)
        return self.register_contribution(slot, payload, plugin_id=plugin_id)

    def register_workspace_panel(self, *, plugin_id=None, **props):
        return self.register_contribution('workspace.panel', props, plugin_id=plugin_id)

    def register_seat_decorator(self, *, plugin_id=None, **props):
        return self.register_contribution('seat.overlay', props, plugin_id=plugin_id)

    def emit(self, event, *, mode=None, **context):
        self.ensure_loaded()
        event_name = str(event or '').strip()
        if not event_name:
            return []
        rows = []
        mutable_context = dict(context)
        cancelled = False
        if event_name == 'app_ready':
            for record in self._plugins.values():
                if not record.enabled:
                    continue
                try:
                    lifecycle_result = self._call_lifecycle(record, 'on_app_ready', **mutable_context)
                    if lifecycle_result is not None:
                        rows.append({
                            'plugin_id': record.plugin_id,
                            'status': 'ok',
                            'kind': 'lifecycle',
                            'result': lifecycle_result,
                        })
                except Exception as exc:
                    rows.append({
                        'plugin_id': record.plugin_id,
                        'status': 'error',
                        'kind': 'lifecycle',
                        'error': str(exc),
                    })
                    LOGGER.exception('插件生命周期执行失败: %s/on_app_ready', record.plugin_id)
        for hook in self._hooks.get(event_name, []):
            record = self._plugins.get(hook.plugin_id)
            if record is None or not record.enabled:
                continue
            if mode and hook.kind != mode:
                continue
            try:
                ctx = self.create_context(hook.plugin_id, event=event_name, **mutable_context)
                result = self._invoke_timed(hook.handler, ctx, hook.stats)
                hook_result = result if isinstance(result, HookResult) else HookResult.continue_(result)
                row = {
                    'plugin_id': hook.plugin_id,
                    'status': 'ok',
                    'priority': hook.priority,
                    'kind': hook.kind,
                    'result': hook_result.to_dict(),
                }
                rows.append(row)
                if hook_result.status == 'modify':
                    mutable_context.update(hook_result.changes)
                if hook_result.status == 'cancel':
                    cancelled = True
                    break
            except Exception as exc:
                rows.append({
                    'plugin_id': hook.plugin_id,
                    'status': 'error',
                    'priority': hook.priority,
                    'kind': hook.kind,
                    'error': str(exc),
                })
                LOGGER.exception('插件 hook 执行失败: %s/%s', hook.plugin_id, event_name)
        if mode == 'intervention':
            reason = ''
            if cancelled and rows:
                reason = ((rows[-1].get('result') or {}).get('reason') or '')
            return {
                'cancelled': cancelled,
                'reason': reason,
                'context': mutable_context,
                'results': rows,
            }
        return rows

    def run_action(self, plugin_id, action, *, method='POST', **context):
        self.ensure_loaded()
        record = self._current_record(plugin_id)
        if not record.enabled:
            raise PluginDisabledError(f'插件已禁用：{record.plugin_id}')
        action_key = str(action or '').strip()
        registration = record.actions.get(action_key)
        if registration is None:
            raise PluginActionNotFoundError(f'插件动作不存在：{record.plugin_id}/{action_key}')
        request_method = str(method or 'POST').upper()
        if request_method not in registration.methods:
            raise PluginMethodNotAllowedError(
                f'插件动作不支持请求方法 {request_method}，仅支持 {",".join(registration.methods)}'
            )
        for capability in registration.permissions:
            self.require_permission(record.plugin_id, capability, request=context.get('request'), classroom=context.get('classroom'))
        ctx = self.create_context(record.plugin_id, action=action_key, **context)
        return self._invoke_timed(registration.handler, ctx, registration.stats)

    def run_command(self, plugin_id, command_id, **context):
        self.ensure_loaded()
        record = self._current_record(plugin_id)
        if not record.enabled:
            raise PluginDisabledError(f'插件已禁用：{record.plugin_id}')
        command_key = str(command_id or '').strip()
        registration = record.commands.get(command_key)
        if registration is None:
            raise PluginActionNotFoundError(f'插件命令不存在：{record.plugin_id}/{command_key}')
        for capability in registration.permissions:
            self.require_permission(record.plugin_id, capability, request=context.get('request'), classroom=context.get('classroom'))
        if registration.action:
            started = time.perf_counter()
            error = None
            try:
                return self.run_action(record.plugin_id, registration.action, method='POST', **context)
            except Exception as exc:
                error = exc
                raise
            finally:
                registration.stats.record((time.perf_counter() - started) * 1000, error=error)
        if registration.handler is None:
            return {'handled_by': 'frontend', 'command_id': command_key}
        ctx = self.create_context(record.plugin_id, command=command_key, **context)
        return self._invoke_timed(registration.handler, ctx, registration.stats)

    def list_commands(self, *, placement='', include_disabled=False):
        self.ensure_loaded()
        rows = []
        for record in sorted(self._plugins.values(), key=lambda item: item.plugin_id):
            if not include_disabled and not record.enabled:
                continue
            for command in sorted(record.commands.values(), key=lambda item: item.command_id):
                if placement and placement not in command.placements:
                    continue
                rows.append({
                    'plugin_id': record.plugin_id,
                    'id': command.command_id,
                    'title': command.title,
                    'description': command.description,
                    'shortcut': command.shortcut,
                    'action': command.action,
                    'placements': list(command.placements),
                    'permissions': list(command.permissions),
                    'stats': command.stats.to_dict(),
                })
        return rows

    def list_contributions(self, *, slot='', include_disabled=False):
        self.ensure_loaded()
        rows = []
        for record in sorted(self._plugins.values(), key=lambda item: item.plugin_id):
            if not include_disabled and not record.enabled:
                continue
            for slot_name, items in record.contributions.items():
                if slot and slot_name != slot:
                    continue
                rows.extend(dict(item) for item in items)
        return rows

    def enable_plugin(self, plugin_id):
        self.ensure_loaded()
        record = self._current_record(plugin_id)
        if not record.enabled:
            record.enabled = True
            self.storage_backend.set(record.plugin_id, '__runtime__', f'{self.runtime_name}.enabled', True)
            self._call_lifecycle(record, 'on_enable')
        return self.serialize_record(record, detailed=True)

    def disable_plugin(self, plugin_id):
        self.ensure_loaded()
        record = self._current_record(plugin_id)
        if record.enabled:
            self._call_lifecycle(record, 'on_disable')
            record.enabled = False
            self.storage_backend.set(record.plugin_id, '__runtime__', f'{self.runtime_name}.enabled', False)
            cache = self._caches.get(record.plugin_id)
            if cache:
                cache.clear()
        return self.serialize_record(record, detailed=True)

    def uninstall_plugin(self, plugin_id, *, clear_data=False):
        self.ensure_loaded()
        record = self._current_record(plugin_id)
        if record.enabled:
            self._call_lifecycle(record, 'on_disable')
        self._call_lifecycle(record, 'on_unload')
        self._call_lifecycle(record, 'on_uninstall')
        record.enabled = False
        record.installed = False
        self.storage_backend.set(record.plugin_id, '__runtime__', f'{self.runtime_name}.enabled', False)
        self.storage_backend.set(record.plugin_id, '__runtime__', f'{self.runtime_name}.installed', False)
        if clear_data:
            self.storage_backend.clear(record.plugin_id)
        return self.serialize_record(record, detailed=True)

    def reload(self, plugin_id=None):
        with self._lock:
            self.ensure_loaded()
            target = str(plugin_id or '').strip()
            if target and target not in self._plugins:
                raise PluginNotFoundError(f'插件不存在：{target}')
            for record in list(self._plugins.values()):
                try:
                    if record.enabled:
                        self._call_lifecycle(record, 'on_disable')
                    self._call_lifecycle(record, 'on_unload')
                except Exception:
                    LOGGER.exception('卸载插件失败: %s', record.plugin_id)
            self._loaded = False
            self._plugins = {}
            self._hooks = {}
            self._load_errors = []
            self._sequence = 0
            self._app_ready_emitted = False
            self.ensure_loaded()
            if target:
                return self.serialize_record(self._current_record(target), detailed=True)
            return self.list_plugins(detailed=True)

    def serialize_record(self, record, *, detailed=False):
        row = {
            'id': record.plugin_id,
            'name': record.name,
            'version': record.version,
            'description': record.manifest.description,
            'author': record.manifest.author,
            'website': record.manifest.website,
            'enabled': record.enabled,
            'installed': record.installed,
            'trust_level': record.manifest.trust_level,
            'api_version': {'min': record.manifest.api_min, 'max': record.manifest.api_max},
            'app_requires': record.manifest.app_requires,
            'permissions': PermissionSet.from_value(record.manifest.permissions).describe(),
            'path': record.path,
            'manifest_path': record.manifest_path,
            'hooks': sorted(record.hooks.keys()),
            'actions': [
                {
                    'name': action.name,
                    'methods': list(action.methods),
                    'description': action.description,
                    'permissions': list(action.permissions),
                    'auth_required': action.auth_required,
                    'stats': action.stats.to_dict(),
                }
                for action in sorted(record.actions.values(), key=lambda item: item.name)
            ],
            'commands': [
                {
                    'id': command.command_id,
                    'title': command.title,
                    'description': command.description,
                    'shortcut': command.shortcut,
                    'action': command.action,
                    'placements': list(command.placements),
                    'permissions': list(command.permissions),
                    'stats': command.stats.to_dict(),
                }
                for command in sorted(record.commands.values(), key=lambda item: item.command_id)
            ],
            'contribution_slots': sorted(record.contributions.keys()),
            'lifecycle': sorted(record.lifecycle.keys()),
            'load_duration_ms': record.load_duration_ms,
            'loaded_at': record.loaded_at,
            'last_error': record.last_error,
        }
        if detailed:
            row['manifest'] = record.manifest.to_dict()
            row['contributions'] = {
                slot: [dict(item) for item in items]
                for slot, items in record.contributions.items()
            }
        return row

    def list_plugins(self, *, detailed=False):
        self.ensure_loaded()
        return [
            self.serialize_record(record, detailed=detailed)
            for record in sorted(self._plugins.values(), key=lambda item: item.plugin_id)
        ]
