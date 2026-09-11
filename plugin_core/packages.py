from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .manifest import PLUGIN_API_VERSION, PluginManifest, load_manifest


class PluginPackageError(Exception):
    pass


MAX_PACKAGE_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_PACKAGE_FILES = 512


def _safe_member_path(name: str) -> Path:
    normalized = str(name or '').replace('\\', '/')
    path = Path(normalized)
    if (
        not normalized
        or normalized.startswith('/')
        or path.is_absolute()
        or '..' in path.parts
        or (path.parts and path.parts[0].endswith(':'))
    ):
        raise PluginPackageError(f'压缩包包含不安全路径：{name}')
    return path


def _file_hashes(root: Path, *, exclude_manifests=True):
    rows = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if exclude_manifests and relative in {'plugin.yaml', 'plugin.yml', 'plugin.json'}:
            continue
        rows[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return rows


def _signature_payload(manifest: PluginManifest, file_hashes):
    return json.dumps(
        {
            'id': manifest.plugin_id,
            'version': manifest.version,
            'files': dict(sorted(file_hashes.items())),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


@dataclass(frozen=True)
class PackageInspection:
    manifest: PluginManifest
    root: Path
    file_hashes: dict[str, str]
    signature_status: str
    signature_key_id: str = ''


class PluginPackageManager:
    def __init__(
        self,
        install_root,
        *,
        backup_root,
        trusted_public_keys=None,
        require_trusted_signature=False,
        app_version='0.0.0',
        api_version=PLUGIN_API_VERSION,
    ):
        self.install_root = Path(install_root).expanduser().resolve()
        self.backup_root = Path(backup_root).expanduser().resolve()
        self.trusted_public_keys = dict(trusted_public_keys or {})
        self.require_trusted_signature = bool(require_trusted_signature)
        self.app_version = str(app_version or '0.0.0')
        self.api_version = int(api_version)

    def _extract(self, package_path: Path, destination: Path):
        if package_path.stat().st_size > MAX_PACKAGE_BYTES:
            raise PluginPackageError('插件包不能超过 25MB')
        with zipfile.ZipFile(package_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_PACKAGE_FILES:
                raise PluginPackageError('插件包文件数量超过 512 个')
            total_size = sum(max(0, int(info.file_size)) for info in infos)
            if total_size > MAX_EXPANDED_BYTES:
                raise PluginPackageError('插件包解压后不能超过 100MB')
            seen_paths = set()
            for info in infos:
                relative = _safe_member_path(info.filename)
                normalized_key = relative.as_posix().casefold().rstrip('/')
                if normalized_key in seen_paths:
                    raise PluginPackageError(f'压缩包包含重复路径：{info.filename}')
                seen_paths.add(normalized_key)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise PluginPackageError('插件包不得包含符号链接')
                target = (destination / relative).resolve()
                if destination.resolve() not in target.parents and target != destination.resolve():
                    raise PluginPackageError('插件包路径越界')
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

    def _locate_root(self, extracted: Path):
        manifests = []
        for name in ('plugin.yaml', 'plugin.yml', 'plugin.json'):
            manifests.extend(extracted.glob(name))
            manifests.extend(extracted.glob(f'*/{name}'))
        unique = sorted(set(path.resolve() for path in manifests))
        if len(unique) != 1:
            raise PluginPackageError('插件包必须且只能包含一个 plugin.yaml/plugin.json')
        return unique[0].parent, unique[0]

    def inspect(self, package_path: Path, extracted: Path):
        self._extract(package_path, extracted)
        root, manifest_path = self._locate_root(extracted)
        data = load_manifest(manifest_path)
        manifest = PluginManifest.from_mapping(data, fallback_id=root.name)
        try:
            manifest.validate_compatibility(self.app_version, self.api_version)
        except Exception as exc:
            raise PluginPackageError(str(exc)) from exc
        hashes = _file_hashes(root)
        integrity = data.get('integrity') or {}
        expected_hashes = integrity.get('files') if isinstance(integrity, dict) else {}
        if expected_hashes:
            normalized_expected = {str(key): str(value).lower() for key, value in expected_hashes.items()}
            if hashes != normalized_expected:
                raise PluginPackageError('插件包文件哈希与 manifest.integrity 不一致')

        signature = manifest.signature
        signature_status = 'unsigned'
        key_id = str(signature.get('key_id') or '') if signature else ''
        if signature:
            if str(signature.get('algorithm') or '').lower() != 'ed25519':
                raise PluginPackageError('插件签名算法仅支持 Ed25519')
            public_key_value = self.trusted_public_keys.get(key_id)
            if not public_key_value:
                raise PluginPackageError(f'插件签名 key_id 未受信任：{key_id}')
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

                public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_value))
                public_key.verify(
                    base64.b64decode(str(signature.get('value') or '')),
                    _signature_payload(manifest, hashes),
                )
            except Exception as exc:
                raise PluginPackageError('插件签名验证失败') from exc
            signature_status = 'verified'
        elif manifest.trust_level == 'trusted' and self.require_trusted_signature:
            raise PluginPackageError('可信 Python 插件必须提供受信任签名')

        if manifest.trust_level == 'sandboxed' and any(path.suffix == '.py' for path in root.rglob('*') if path.is_file()):
            raise PluginPackageError('sandboxed 扩展不得包含 Python 文件')
        return PackageInspection(manifest, root, hashes, signature_status, key_id)

    def install(self, package_bytes: bytes, *, update=False, confirm_trusted=False):
        if not isinstance(package_bytes, (bytes, bytearray)) or not package_bytes:
            raise PluginPackageError('插件包为空')
        self.install_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='fuckseats-plugin-package-') as temp_dir:
            temp_root = Path(temp_dir)
            package_path = temp_root / 'plugin.zip'
            package_path.write_bytes(bytes(package_bytes))
            inspection = self.inspect(package_path, temp_root / 'extracted')
            manifest = inspection.manifest
            if manifest.trust_level == 'trusted' and not confirm_trusted:
                raise PluginPackageError('安装可信 Python 插件需要显式确认其可访问主进程能力')
            target = (self.install_root / manifest.plugin_id).resolve()
            if target.parent != self.install_root:
                raise PluginPackageError('插件安装路径无效')
            exists = target.exists()
            if exists and not update:
                raise PluginPackageError('插件已存在，请使用更新操作')
            if not exists and update:
                raise PluginPackageError('插件尚未安装，请使用安装操作')

            backup = None
            if exists:
                backup = self.backup_root / f'{manifest.plugin_id}-{time.time_ns()}'
                shutil.copytree(target, backup)
            staged_target = self.install_root / f'.{manifest.plugin_id}.installing-{os.getpid()}'
            if staged_target.exists():
                shutil.rmtree(staged_target)
            shutil.copytree(inspection.root, staged_target)
            try:
                if target.exists():
                    shutil.rmtree(target)
                os.replace(staged_target, target)
            except Exception:
                if staged_target.exists():
                    shutil.rmtree(staged_target)
                if backup and backup.exists() and not target.exists():
                    shutil.copytree(backup, target)
                raise
            return {
                'id': manifest.plugin_id,
                'name': manifest.name,
                'version': manifest.version,
                'operation': 'update' if exists else 'install',
                'signature_status': inspection.signature_status,
                'signature_key_id': inspection.signature_key_id,
                'path': str(target),
                'backup_path': str(backup or ''),
            }

    def remove(self, plugin_id: str):
        target = (self.install_root / str(plugin_id or '').strip()).resolve()
        if target.parent != self.install_root or not target.exists() or not target.is_dir():
            raise PluginPackageError('插件安装目录不存在')
        self.backup_root.mkdir(parents=True, exist_ok=True)
        backup = self.backup_root / f'{target.name}-removed-{time.time_ns()}'
        shutil.move(str(target), str(backup))
        return {'id': target.name, 'removed': True, 'backup_path': str(backup)}


def fetch_marketplace_index(url: str, *, timeout=5):
    parsed = urllib.parse.urlparse(str(url or '').strip())
    if parsed.scheme != 'https' or not parsed.netloc:
        raise PluginPackageError('插件市场地址必须使用 HTTPS')
    request = urllib.request.Request(
        parsed.geturl(),
        headers={'Accept': 'application/json', 'User-Agent': 'FuckSeats-Plugin-API/1'},
    )
    with urllib.request.urlopen(request, timeout=max(1, min(15, int(timeout)))) as response:
        if int(getattr(response, 'status', 200)) != 200:
            raise PluginPackageError('插件市场返回异常状态')
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise PluginPackageError('插件市场索引超过 2MB')
    try:
        payload = json.loads(raw.decode('utf-8'))
    except Exception as exc:
        raise PluginPackageError('插件市场索引不是有效 JSON') from exc
    if not isinstance(payload, dict) or not isinstance(payload.get('plugins'), list):
        raise PluginPackageError('插件市场索引缺少 plugins 数组')
    return payload
