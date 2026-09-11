from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .permissions import PermissionSet


class _PermissionedResource:
    def __init__(self, ctx, capability, resource):
        self._ctx = ctx
        self._capability = capability
        self._resource = resource

    def __getattr__(self, name):
        value = getattr(self._resource, name)
        if not callable(value):
            self._ctx.require_permission(self._capability)
            return value

        def guarded(*args, **kwargs):
            self._ctx.require_permission(self._capability)
            return value(*args, **kwargs)
        return guarded


@dataclass
class PluginContext(Mapping):
    plugin_id: str
    registry: Any
    plugin: Any
    request: Any = None
    payload: dict[str, Any] = field(default_factory=dict)
    classroom: Any = None
    user: Any = None
    services: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        bundle = self.registry.get_storage_bundle(self.plugin_id)
        self.logger = logging.getLogger(f'fuckseats.plugin.{self.plugin_id}')
        self.permissions = PermissionSet.from_value(self.plugin.manifest.permissions)
        self.storage = _PermissionedResource(self, 'storage', bundle.storage)
        self.settings = _PermissionedResource(self, 'settings', bundle.settings)
        self.secrets = _PermissionedResource(self, 'secrets', bundle.secrets)
        self.cache = _PermissionedResource(self, 'cache', bundle.cache)

    def require_permission(self, capability: str):
        return self.registry.require_permission(
            self.plugin_id,
            capability,
            request=self.request,
            classroom=self.classroom,
        )

    def attach_service(self, name: str, service: Any):
        key = str(name or '').strip()
        if not key or key.startswith('_'):
            raise ValueError('服务名称无效')
        self.services[key] = service
        setattr(self, key, service)
        return service

    def to_dict(self):
        result = {
            'ctx': self,
            'context': self,
            'plugin': self.plugin,
            'plugin_id': self.plugin_id,
            'registry': self.registry,
            'logger': self.logger,
            'storage': self.storage,
            'settings': self.settings,
            'secrets': self.secrets,
            'cache': self.cache,
            'permissions': self.permissions,
            'services': self.services,
            'request': self.request,
            'payload': self.payload,
            'classroom': self.classroom,
            'user': self.user,
        }
        result.update(self.extra)
        return result

    def __getitem__(self, key):
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self):
        return len(self.to_dict())

    def get(self, key, default=None):
        return self.to_dict().get(key, default)
