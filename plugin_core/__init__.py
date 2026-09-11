"""FuckSeats 本地端与云端共用的 Plugin API v1。"""

from .actions import ActionRegistration, CommandRegistration, ExecutionStats
from .context import PluginContext
from .errors import (
    PluginActionNotFoundError,
    PluginCompatibilityError,
    PluginDisabledError,
    PluginError,
    PluginMethodNotAllowedError,
    PluginNotFoundError,
    PluginPermissionError,
)
from .events import HookRegistration, HookResult
from .manifest import (
    PLUGIN_API_VERSION,
    PluginCandidate,
    PluginManifest,
    discover_plugin_candidates,
    load_manifest,
)
from .permissions import KNOWN_CAPABILITIES, PermissionSet
from .packages import PluginPackageError, PluginPackageManager, fetch_marketplace_index
from .registry import BasePluginRecord, BasePluginRegistry
from .storage import (
    DjangoModelStorageBackend,
    MemoryStorageBackend,
    PluginStorageBundle,
)

__all__ = [
    'ActionRegistration',
    'BasePluginRecord',
    'BasePluginRegistry',
    'CommandRegistration',
    'DjangoModelStorageBackend',
    'ExecutionStats',
    'HookRegistration',
    'HookResult',
    'KNOWN_CAPABILITIES',
    'MemoryStorageBackend',
    'PLUGIN_API_VERSION',
    'PermissionSet',
    'PluginActionNotFoundError',
    'PluginCandidate',
    'PluginCompatibilityError',
    'PluginContext',
    'PluginDisabledError',
    'PluginError',
    'PluginManifest',
    'PluginMethodNotAllowedError',
    'PluginNotFoundError',
    'PluginPackageError',
    'PluginPackageManager',
    'PluginPermissionError',
    'PluginStorageBundle',
    'discover_plugin_candidates',
    'load_manifest',
    'fetch_marketplace_index',
]
