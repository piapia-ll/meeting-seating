from __future__ import annotations

from dataclasses import dataclass

from .errors import PluginPermissionError


KNOWN_CAPABILITIES = {
    'plugin.runtime',
    'classroom.read',
    'classroom.write',
    'students.read',
    'students.write',
    'layout.read',
    'layout.write',
    'workspace.ui',
    'workspace.dom',
    'workspace.shortcuts',
    'workspace.toolbar',
    'workspace.sidebar',
    'workspace.command_palette',
    'workspace.context_menu',
    'seat.badge',
    'seat.overlay',
    'network',
    'filesystem',
    'clipboard',
    'cloud.account',
    'storage',
    'settings',
    'secrets',
    'cache',
}


CAPABILITY_LABELS = {
    'plugin.runtime': '调用插件运行时',
    'classroom.read': '读取班级信息',
    'classroom.write': '修改班级信息',
    'students.read': '读取学生信息',
    'students.write': '修改学生信息',
    'layout.read': '读取座位布局',
    'layout.write': '修改座位布局',
    'workspace.ui': '在工作区显示界面',
    'workspace.dom': '直接修改工作区页面',
    'workspace.shortcuts': '注册工作区快捷键',
    'workspace.toolbar': '向工作区工具栏添加入口',
    'workspace.sidebar': '向工作区侧栏添加内容',
    'workspace.command_palette': '注册命令面板命令',
    'workspace.context_menu': '添加上下文菜单',
    'seat.badge': '显示座位徽标',
    'seat.overlay': '显示座位覆盖层',
    'network': '访问网络',
    'filesystem': '访问文件系统',
    'clipboard': '访问剪贴板',
    'cloud.account': '访问云账户',
    'storage': '保存插件数据',
    'settings': '保存插件设置',
    'secrets': '保存插件密钥',
    'cache': '使用临时缓存',
}


@dataclass(frozen=True)
class PermissionSet:
    values: frozenset[str]

    @classmethod
    def from_value(cls, value):
        if isinstance(value, str):
            value = [value]
        rows = frozenset(str(item).strip() for item in (value or []) if str(item).strip())
        return cls(rows)

    def allows(self, capability: str, *, legacy_trusted: bool = False) -> bool:
        key = str(capability or '').strip()
        if not key:
            return True
        if '*' in self.values or key in self.values:
            return True
        prefix = key.split('.', 1)[0] + '.*'
        if prefix in self.values:
            return True
        return bool(legacy_trusted and not self.values)

    def require(self, capability: str, *, plugin_id: str = '', legacy_trusted: bool = False):
        if not self.allows(capability, legacy_trusted=legacy_trusted):
            label = CAPABILITY_LABELS.get(capability, capability)
            raise PluginPermissionError(f'插件 {plugin_id or "unknown"} 未声明权限：{label}')

    def describe(self):
        return [
            {'id': item, 'label': CAPABILITY_LABELS.get(item, item), 'known': item in KNOWN_CAPABILITIES}
            for item in sorted(self.values)
        ]
