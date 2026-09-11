from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import PluginCompatibilityError, PluginManifestError

try:
    import yaml
except Exception:  # pragma: no cover - 由调用方给出明确缺依赖错误
    yaml = None


PLUGIN_API_VERSION = 1
PLUGIN_ID_RE = re.compile(r'^[a-z][a-z0-9_.-]{1,63}$')
VERSION_RE = re.compile(r'\d+')


def _version_tuple(value) -> tuple[int, ...]:
    parts = tuple(int(item) for item in VERSION_RE.findall(str(value or '')))
    return parts or (0,)


def _compare_version(left, right) -> int:
    left_parts = list(_version_tuple(left))
    right_parts = list(_version_tuple(right))
    size = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (size - len(left_parts)))
    right_parts.extend([0] * (size - len(right_parts)))
    return (left_parts > right_parts) - (left_parts < right_parts)


def version_matches(version: str, expression: str) -> bool:
    """支持插件协议所需的轻量版本区间：>=、>、<=、<、==、!= 与逗号组合。"""
    text = str(expression or '').strip()
    if not text or text == '*':
        return True
    for raw_rule in text.split(','):
        rule = raw_rule.strip()
        if not rule:
            continue
        match = re.match(r'^(>=|<=|==|!=|>|<|~=)?\s*([0-9][0-9A-Za-z_.+-]*)$', rule)
        if not match:
            raise PluginManifestError(f'不支持的版本约束：{rule}')
        operator = match.group(1) or '=='
        target = match.group(2)
        compared = _compare_version(version, target)
        if operator == '>=' and compared < 0:
            return False
        if operator == '<=' and compared > 0:
            return False
        if operator == '>' and compared <= 0:
            return False
        if operator == '<' and compared >= 0:
            return False
        if operator == '==' and compared != 0:
            return False
        if operator == '!=' and compared == 0:
            return False
        if operator == '~=':
            version_parts = _version_tuple(version)
            target_parts = _version_tuple(target)
            if compared < 0 or version_parts[:max(1, len(target_parts) - 1)] != target_parts[:max(1, len(target_parts) - 1)]:
                return False
    return True


def _string_list(value) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]
    return tuple(str(item).strip() for item in (value or []) if str(item).strip())


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    api_min: int = PLUGIN_API_VERSION
    api_max: int = PLUGIN_API_VERSION
    app_requires: str = ''
    entry: str = 'plugin.py'
    description: str = ''
    author: str = ''
    website: str = ''
    license: str = ''
    icon: str = ''
    update_url: str = ''
    trust_level: str = 'trusted'
    permissions: tuple[str, ...] = ()
    dependencies: dict[str, str] = field(default_factory=dict)
    contributes: dict[str, Any] = field(default_factory=dict)
    django: dict[str, Any] = field(default_factory=dict)
    signature: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    source: str = 'manifest'

    @classmethod
    def from_mapping(cls, mapping, *, fallback_id='', source='manifest'):
        data = dict(mapping or {})
        plugin_id = str(data.get('id') or fallback_id or '').strip()
        if not plugin_id:
            raise PluginManifestError('插件 ID 不能为空')
        if not PLUGIN_ID_RE.match(plugin_id):
            raise PluginManifestError(f'插件 ID 格式错误：{plugin_id}')

        api_value = data.get('api')
        if isinstance(api_value, dict):
            api_min = int(api_value.get('min', PLUGIN_API_VERSION))
            api_max = int(api_value.get('max', api_min))
        else:
            api_version = data.get('api_version', PLUGIN_API_VERSION)
            api_min = api_max = int(api_version)
        if api_min <= 0 or api_max < api_min:
            raise PluginManifestError('Plugin API 版本范围无效')

        requires = data.get('requires') or {}
        if isinstance(requires, str):
            app_requires = requires
            dependencies = {}
        elif isinstance(requires, dict):
            app_requires = str(requires.get('app') or '')
            dependency_value = requires.get('plugins') or data.get('dependencies') or {}
            if isinstance(dependency_value, list):
                dependencies = {str(item): '*' for item in dependency_value}
            elif isinstance(dependency_value, dict):
                dependencies = {str(key): str(value or '*') for key, value in dependency_value.items()}
            else:
                dependencies = {}
        else:
            app_requires = ''
            dependencies = {}

        trust_level = str(data.get('trust_level') or data.get('trust') or 'trusted').strip().lower()
        if trust_level not in {'trusted', 'sandboxed'}:
            raise PluginManifestError('trust_level 仅支持 trusted 或 sandboxed')

        entry = str(data.get('entry') or 'plugin.py').strip().replace('\\', '/')
        entry_path = PurePosixPath(entry)
        if (
            not entry
            or entry_path.is_absolute()
            or '..' in entry_path.parts
            or (entry_path.parts and entry_path.parts[0].endswith(':'))
            or entry_path.suffix.lower() != '.py'
        ):
            raise PluginManifestError('entry 必须是插件目录内的 Python 相对路径')

        contributes = data.get('contributes') or {}
        if not isinstance(contributes, dict):
            raise PluginManifestError('contributes 必须是对象')

        return cls(
            plugin_id=plugin_id,
            name=str(data.get('name') or plugin_id),
            version=str(data.get('version') or '0.0.1'),
            api_min=api_min,
            api_max=api_max,
            app_requires=app_requires,
            entry=entry,
            description=str(data.get('description') or ''),
            author=str(data.get('author') or ''),
            website=str(data.get('website') or data.get('homepage') or ''),
            license=str(data.get('license') or ''),
            icon=str(data.get('icon') or ''),
            update_url=str(data.get('update_url') or ''),
            trust_level=trust_level,
            permissions=_string_list(data.get('permissions')),
            dependencies=dependencies,
            contributes=dict(contributes),
            django=dict(data.get('django') or {}),
            signature=dict(data.get('signature') or {}),
            raw=data,
            source=source,
        )

    def validate_compatibility(self, app_version: str, api_version: int = PLUGIN_API_VERSION):
        if not (self.api_min <= int(api_version) <= self.api_max):
            raise PluginCompatibilityError(
                f'{self.plugin_id} 需要 Plugin API {self.api_min}-{self.api_max}，当前为 {api_version}'
            )
        app_version_text = str(app_version or '').strip()
        app_version_known = bool(app_version_text) and not (
            app_version_text.startswith('0.0.0') or app_version_text.lower() in {'dev', 'local', 'unknown'}
        )
        if self.app_requires and app_version_known and not version_matches(app_version_text, self.app_requires):
            raise PluginCompatibilityError(
                f'{self.plugin_id} 需要 FuckSeats {self.app_requires}，当前为 {app_version}'
            )

    def to_dict(self):
        return {
            'id': self.plugin_id,
            'name': self.name,
            'version': self.version,
            'api': {'min': self.api_min, 'max': self.api_max},
            'requires': {'app': self.app_requires, 'plugins': dict(self.dependencies)},
            'entry': self.entry,
            'description': self.description,
            'author': self.author,
            'website': self.website,
            'license': self.license,
            'icon': self.icon,
            'update_url': self.update_url,
            'trust_level': self.trust_level,
            'permissions': list(self.permissions),
            'contributes': dict(self.contributes),
            'django': dict(self.django),
            'signature': dict(self.signature),
            'source': self.source,
        }


@dataclass(frozen=True)
class PluginCandidate:
    root: Path
    entry_path: Path | None
    manifest_path: Path | None
    manifest_data: dict[str, Any]


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        if path.suffix.lower() == '.json':
            value = json.loads(path.read_text(encoding='utf-8')) or {}
        elif path.suffix.lower() in {'.yaml', '.yml'}:
            if yaml is None:
                raise PluginManifestError('读取 plugin.yaml 需要安装 PyYAML')
            value = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        else:
            raise PluginManifestError(f'不支持的 manifest 文件：{path.name}')
    except PluginManifestError:
        raise
    except Exception as exc:
        raise PluginManifestError(f'读取插件 manifest 失败：{path}: {exc}') from exc
    if not isinstance(value, dict):
        raise PluginManifestError('插件 manifest 根节点必须是对象')
    return value


def discover_plugin_candidates(plugin_dirs) -> list[PluginCandidate]:
    rows: list[PluginCandidate] = []
    for raw_path in plugin_dirs:
        if not raw_path:
            continue
        plugin_dir = Path(raw_path).expanduser()
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            continue
        for child in sorted(plugin_dir.iterdir(), key=lambda item: item.name):
            if child.name.startswith('_'):
                continue
            if child.is_file() and child.suffix == '.py' and child.name != '__init__.py':
                rows.append(PluginCandidate(child.parent, child, None, {}))
                continue
            if not child.is_dir():
                continue
            manifest_path = None
            manifest_data = {}
            for manifest_name in ('plugin.yaml', 'plugin.yml', 'plugin.json'):
                candidate_path = child / manifest_name
                if candidate_path.exists():
                    manifest_path = candidate_path
                    manifest_data = load_manifest(candidate_path)
                    break
            entry_name = str(manifest_data.get('entry') or 'plugin.py')
            entry_path = child / entry_name
            if not entry_path.exists():
                init_path = child / '__init__.py'
                entry_path = init_path if init_path.exists() else None
            if entry_path is not None or manifest_data:
                rows.append(PluginCandidate(child, entry_path, manifest_path, manifest_data))
    return rows
