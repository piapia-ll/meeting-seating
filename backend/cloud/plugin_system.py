from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver
from django.views.decorators.http import require_http_methods

from plugin_core import (
    BasePluginRegistry,
    DjangoModelStorageBackend,
    PluginActionNotFoundError,
    PluginDisabledError,
    PluginMethodNotAllowedError,
    PluginNotFoundError,
)
from plugin_core.actions import ExecutionStats, normalize_methods
from plugin_core.manifest import discover_plugin_candidates

from .config import get_config
from .plugin_services import cloud_plugin_service_factories


LOGGER = logging.getLogger(__name__)


class BackendPluginAuthenticationError(Exception):
    pass


BackendPluginError = Exception
BackendPluginNotFoundError = PluginNotFoundError
BackendPluginActionNotFoundError = PluginActionNotFoundError
BackendPluginMethodNotAllowedError = PluginMethodNotAllowedError


@dataclass
class BackendPluginRoute:
    route: str
    handler: Callable[..., Any]
    methods: tuple[str, ...] = ('GET',)
    name: str = ''
    description: str = ''
    permissions: tuple[str, ...] = ()
    auth_required: bool = False
    stats: ExecutionStats = field(default_factory=ExecutionStats)


def _json_error(message, status=400, **extra):
    payload = {'ok': False, 'status': 'error', 'message': str(message)}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _json_body(request):
    try:
        value = json.loads((request.body or b'{}').decode('utf-8') or '{}')
    except Exception as exc:
        raise ValueError('请求数据格式错误') from exc
    if not isinstance(value, dict):
        raise ValueError('请求数据必须是 JSON 对象')
    return value


def _normalize_response(value):
    if isinstance(value, (HttpResponse, JsonResponse)):
        return value
    if value is None:
        value = {'ok': True, 'status': 'success'}
    if isinstance(value, dict):
        payload = dict(value)
        payload.setdefault('ok', True)
        payload.setdefault('status', 'success')
        return JsonResponse(payload)
    if isinstance(value, (list, tuple)):
        return JsonResponse({'ok': True, 'status': 'success', 'data': list(value)})
    return JsonResponse({'ok': True, 'status': 'success', 'data': value})


def _session_context(request, auth_required):
    if not auth_required:
        return {}
    if request is None:
        raise BackendPluginAuthenticationError('此插件能力需要登录态')
    from .auth import get_request_session

    session = get_request_session(request)
    if not session:
        raise BackendPluginAuthenticationError('session_token 无效或已过期')
    request.cloud_session = session
    request.cloud_user = session.user
    return {
        'session': session,
        'user': session.user,
        'cloud_session': session,
        'cloud_user': session.user,
    }


def _plugin_config():
    return get_config().get('plugins', {}) or {}


def _split_env_paths(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _resolve_plugin_dirs(base_dir=None):
    base = Path(base_dir or getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)).resolve()
    configured = []
    django_dirs = getattr(settings, 'CLOUD_PLUGIN_DIRS', None)
    if django_dirs:
        configured.extend(django_dirs)
    config_dirs = _plugin_config().get('dirs') or []
    if isinstance(config_dirs, str):
        config_dirs = [config_dirs]
    configured.extend(config_dirs)
    configured.extend(_split_env_paths(os.getenv('CLOUD_PLUGIN_DIRS')))
    if not configured:
        configured = [base / 'plugins']
    rows = []
    for raw_path in configured:
        value = Path(raw_path).expanduser()
        if not value.is_absolute():
            value = base / value
        rows.append(value.resolve())
    return rows


def _manifest_list_value(manifest, key):
    value = manifest.get(key)
    if value is None:
        value = (manifest.get('django') or {}).get(key)
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item).strip()]


def get_plugin_installed_apps(base_dir=None):
    apps = []
    for candidate in discover_plugin_candidates(_resolve_plugin_dirs(base_dir)):
        apps.extend(_manifest_list_value(candidate.manifest_data, 'installed_apps'))
    return apps


def get_plugin_middleware(base_dir=None):
    middleware = []
    for candidate in discover_plugin_candidates(_resolve_plugin_dirs(base_dir)):
        middleware.extend(_manifest_list_value(candidate.manifest_data, 'middleware'))
    return middleware


def _cloud_app_version():
    env_value = str(os.getenv('FUCKSEATS_APP_VERSION') or os.getenv('CLOUD_APP_VERSION') or '').strip()
    if env_value:
        return env_value
    manifest_path = Path(__file__).resolve().parents[2] / 'runtime' / 'release.json'
    try:
        return str(json.loads(manifest_path.read_text(encoding='utf-8')).get('version') or '0.0.0')
    except Exception:
        return '0.0.0'


def _plugin_storage_model():
    from .models import PluginRuntimeKV

    return PluginRuntimeKV


def _plugin_storage_secret():
    return str(getattr(settings, 'SECRET_KEY', 'fuckseats-cloud-plugin-storage'))


class BackendPluginRegistry(BasePluginRegistry):
    runtime_name = 'cloud'

    def __init__(self):
        super().__init__(
            app_version=_cloud_app_version(),
            storage_backend=DjangoModelStorageBackend(_plugin_storage_model, _plugin_storage_secret),
            services=cloud_plugin_service_factories(),
        )

    def resolve_plugin_dirs(self):
        return _resolve_plugin_dirs()

    def get_state(self, plugin_id=None):
        return self._current_record(plugin_id).state

    def register_route(
        self,
        route,
        handler,
        *,
        methods=('GET',),
        name='',
        description='',
        permissions=(),
        auth_required=False,
        plugin_id=None,
    ):
        record = self._current_record(plugin_id)
        if not callable(handler):
            raise ValueError('route handler 必须是可调用对象')
        route_key = str(route or '').strip().lstrip('/')
        if not route_key:
            raise ValueError('route 不能为空')
        if route_key in record.routes:
            raise ValueError(f'重复 route：{route_key}')
        permission_rows = tuple(str(item) for item in (permissions or ()) if str(item).strip())
        for capability in permission_rows:
            self.require_permission(record.plugin_id, capability)
        record.routes[route_key] = BackendPluginRoute(
            route=route_key,
            handler=handler,
            methods=normalize_methods(methods, default=('GET',)),
            name=str(name or route_key.replace('/', '_').replace('-', '_').replace('<', '').replace('>', '').replace(':', '_')),
            description=str(description or ''),
            permissions=permission_rows,
            auth_required=bool(auth_required),
        )

    def route(self, route, **options):
        def decorator(func):
            self.register_route(route, func, **options)
            return func
        return decorator

    def register_urlpattern(self, pattern, plugin_id=None):
        record = self._current_record(plugin_id)
        if not isinstance(pattern, (URLPattern, URLResolver)):
            raise ValueError('urlpattern 必须由 django.urls.path/re_path/include 创建')
        record.url_patterns.append(pattern)

    def register_urlpatterns(self, patterns, plugin_id=None):
        for pattern in patterns or []:
            self.register_urlpattern(pattern, plugin_id=plugin_id)

    def _register_module(self, record):
        super()._register_module(record)
        if record.module is not None:
            module_urlpatterns = getattr(record.module, 'urlpatterns', None)
            if module_urlpatterns:
                self.register_urlpatterns(module_urlpatterns, plugin_id=record.plugin_id)

    def run_action(self, plugin_id, action, *, method='POST', request=None, payload=None, **context):
        self.ensure_loaded()
        record = self._current_record(plugin_id)
        registration = record.actions.get(str(action or '').strip())
        if registration is None:
            raise BackendPluginActionNotFoundError(f'后端插件动作不存在：{plugin_id}/{action}')
        auth_context = _session_context(request, registration.auth_required)
        return super().run_action(
            plugin_id,
            action,
            method=method,
            request=request,
            payload=payload if isinstance(payload, dict) else {},
            **auth_context,
            **context,
        )

    def _build_route_view(self, plugin_id, plugin_route):
        @require_http_methods(plugin_route.methods)
        def view(request, *args, **kwargs):
            try:
                payload = _json_body(request) if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else {}
                record = self._current_record(plugin_id)
                if not record.enabled:
                    raise PluginDisabledError(f'插件已禁用：{plugin_id}')
                auth_context = _session_context(request, plugin_route.auth_required)
                for capability in plugin_route.permissions:
                    self.require_permission(plugin_id, capability, request=request)
                ctx = self.create_context(
                    plugin_id,
                    request=request,
                    payload=payload,
                    route=plugin_route.route,
                    args=args,
                    kwargs=kwargs,
                    **auth_context,
                    **kwargs,
                )
                result = self._invoke_timed(plugin_route.handler, ctx, plugin_route.stats)
                return _normalize_response(result)
            except BackendPluginAuthenticationError as exc:
                return _json_error(exc, status=401, error='unauthorized')
            except PluginDisabledError as exc:
                return _json_error(exc, status=409, error='plugin_disabled')
            except Exception as exc:
                LOGGER.exception('后端插件路由执行失败: %s/%s', plugin_id, plugin_route.route)
                return _json_error(exc, status=500)
        return view

    def serialize_record(self, record, *, detailed=False):
        row = super().serialize_record(record, detailed=detailed)
        row['routes'] = [
            {
                'route': route.route,
                'methods': list(route.methods),
                'name': route.name,
                'description': route.description,
                'permissions': list(route.permissions),
                'auth_required': route.auth_required,
                'stats': route.stats.to_dict(),
            }
            for route in sorted(record.routes.values(), key=lambda item: item.route)
        ]
        row['url_patterns'] = len(record.url_patterns)
        return row

    def get_urlpatterns(self):
        self.ensure_loaded()
        patterns = [
            path('api/plugins', backend_plugins_list, name='backend_plugins_list'),
            path('api/plugins/commands', backend_plugins_commands, name='backend_plugins_commands'),
            path('api/plugins/contributions', backend_plugins_contributions, name='backend_plugins_contributions'),
            path('api/plugins/<str:plugin_id>/actions/<str:action>', backend_plugins_action, name='backend_plugins_action'),
            path('api/plugins/<str:plugin_id>/commands/<path:command_id>', backend_plugins_command, name='backend_plugins_command'),
            path('api/plugins/<str:plugin_id>/control', backend_plugins_control, name='backend_plugins_control'),
        ]
        for record in sorted(self._plugins.values(), key=lambda item: item.plugin_id):
            for route in sorted(record.routes.values(), key=lambda item: item.route):
                route_name = f'backend_plugin_{record.plugin_id}_{route.name}'.replace('-', '_')
                patterns.append(path(route.route, self._build_route_view(record.plugin_id, route), name=route_name))
            patterns.extend(record.url_patterns)
        return patterns


backend_plugin_registry = BackendPluginRegistry()


def _require_admin(request):
    configured = str(os.getenv('CLOUD_PLUGIN_ADMIN_TOKEN') or '').strip()
    supplied = str(request.headers.get('X-Plugin-Admin-Token') or '').strip()
    if not configured or not supplied or not hmac.compare_digest(configured, supplied):
        raise BackendPluginAuthenticationError('插件管理凭据无效')


@require_http_methods(['GET'])
def backend_plugins_list(request):
    return JsonResponse({
        'ok': True,
        'status': 'success',
        'plugin_api_version': backend_plugin_registry.api_version,
        'app_version': backend_plugin_registry.app_version,
        'plugins': backend_plugin_registry.list_plugins(detailed=True),
        'load_errors': backend_plugin_registry.load_errors,
    })


@require_http_methods(['GET'])
def backend_plugins_commands(request):
    return JsonResponse({
        'ok': True,
        'status': 'success',
        'commands': backend_plugin_registry.list_commands(placement=request.GET.get('placement', '')),
    })


@require_http_methods(['GET'])
def backend_plugins_contributions(request):
    return JsonResponse({
        'ok': True,
        'status': 'success',
        'contributions': backend_plugin_registry.list_contributions(slot=request.GET.get('slot', '')),
    })


@require_http_methods(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def backend_plugins_action(request, plugin_id, action):
    try:
        payload = _json_body(request) if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else dict(request.GET.items())
        result = backend_plugin_registry.run_action(
            plugin_id, action, method=request.method, request=request, payload=payload,
        )
        return _normalize_response(result)
    except (BackendPluginNotFoundError, BackendPluginActionNotFoundError) as exc:
        return _json_error(exc, status=404)
    except BackendPluginMethodNotAllowedError as exc:
        return _json_error(exc, status=405)
    except BackendPluginAuthenticationError as exc:
        return _json_error(exc, status=401, error='unauthorized')
    except PluginDisabledError as exc:
        return _json_error(exc, status=409, error='plugin_disabled')
    except ValueError as exc:
        return _json_error(exc)
    except Exception as exc:
        LOGGER.exception('后端插件 action 执行失败: %s/%s', plugin_id, action)
        return _json_error(exc, status=500)


@require_http_methods(['POST'])
def backend_plugins_command(request, plugin_id, command_id):
    try:
        payload = _json_body(request)
        result = backend_plugin_registry.run_command(
            plugin_id,
            command_id,
            request=request,
            payload=payload,
        )
        return _normalize_response(result)
    except (PluginNotFoundError, PluginActionNotFoundError) as exc:
        return _json_error(exc, status=404)
    except PluginDisabledError as exc:
        return _json_error(exc, status=409, error='plugin_disabled')
    except ValueError as exc:
        return _json_error(exc)
    except Exception as exc:
        LOGGER.exception('后端插件 command 执行失败: %s/%s', plugin_id, command_id)
        return _json_error(exc, status=500)


@require_http_methods(['POST'])
def backend_plugins_control(request, plugin_id):
    try:
        _require_admin(request)
        payload = _json_body(request)
        operation = str(payload.get('operation') or '').strip().lower()
        if operation == 'enable':
            result = backend_plugin_registry.enable_plugin(plugin_id)
        elif operation == 'disable':
            result = backend_plugin_registry.disable_plugin(plugin_id)
        elif operation == 'reload':
            result = backend_plugin_registry.reload(plugin_id)
        elif operation == 'uninstall':
            result = backend_plugin_registry.uninstall_plugin(plugin_id, clear_data=bool(payload.get('clear_data')))
        else:
            return _json_error('operation 仅支持 enable、disable、reload、uninstall')
        return JsonResponse({'ok': True, 'status': 'success', 'plugin': result})
    except BackendPluginAuthenticationError as exc:
        return _json_error(exc, status=401, error='unauthorized')
    except PluginNotFoundError as exc:
        return _json_error(exc, status=404)
    except ValueError as exc:
        return _json_error(exc)
    except Exception as exc:
        LOGGER.exception('后端插件管理失败: %s', plugin_id)
        return _json_error(exc, status=500)
