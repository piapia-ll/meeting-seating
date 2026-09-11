from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .actions import ExecutionStats


@dataclass(frozen=True)
class HookResult:
    status: str = 'continue'
    reason: str = ''
    changes: dict[str, Any] = field(default_factory=dict)
    data: Any = None

    @classmethod
    def cancel(cls, reason: str, data: Any = None):
        return cls(status='cancel', reason=str(reason or '操作已被插件取消'), data=data)

    @classmethod
    def modify(cls, changes: dict[str, Any], data: Any = None):
        if not isinstance(changes, dict):
            raise ValueError('HookResult.modify 的 changes 必须是 dict')
        return cls(status='modify', changes=dict(changes), data=data)

    @classmethod
    def continue_(cls, data: Any = None):
        return cls(status='continue', data=data)

    def to_dict(self):
        result = {'status': self.status}
        if self.reason:
            result['reason'] = self.reason
        if self.changes:
            result['changes'] = dict(self.changes)
        if self.data is not None:
            result['data'] = self.data
        return result


@dataclass
class HookRegistration:
    plugin_id: str
    event: str
    handler: Callable[..., Any]
    priority: int = 0
    kind: str = 'notification'
    sequence: int = 0
    stats: ExecutionStats = field(default_factory=ExecutionStats)
