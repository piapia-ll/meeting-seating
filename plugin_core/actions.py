from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


def normalize_methods(methods, default=('POST',)) -> tuple[str, ...]:
    if isinstance(methods, str):
        methods = [methods]
    rows = tuple(sorted({str(item).strip().upper() for item in (methods or []) if str(item).strip()}))
    return rows or tuple(default)


@dataclass
class ExecutionStats:
    count: int = 0
    errors: int = 0
    total_duration_ms: float = 0.0
    last_duration_ms: float = 0.0
    last_executed_at: str = ''
    last_error: str = ''

    def record(self, duration_ms: float, error: Exception | None = None):
        self.count += 1
        self.total_duration_ms += max(0.0, float(duration_ms or 0.0))
        self.last_duration_ms = round(max(0.0, float(duration_ms or 0.0)), 3)
        self.last_executed_at = datetime.now(timezone.utc).isoformat()
        if error is not None:
            self.errors += 1
            self.last_error = str(error)

    def to_dict(self):
        average = self.total_duration_ms / self.count if self.count else 0.0
        return {
            'count': self.count,
            'errors': self.errors,
            'average_duration_ms': round(average, 3),
            'last_duration_ms': self.last_duration_ms,
            'last_executed_at': self.last_executed_at,
            'last_error': self.last_error,
        }


@dataclass
class ActionRegistration:
    name: str
    handler: Callable[..., Any]
    methods: tuple[str, ...] = ('POST',)
    description: str = ''
    permissions: tuple[str, ...] = ()
    auth_required: bool = False
    stats: ExecutionStats = field(default_factory=ExecutionStats)


@dataclass
class CommandRegistration:
    command_id: str
    title: str
    description: str = ''
    shortcut: str = ''
    handler: Callable[..., Any] | None = None
    action: str = ''
    placements: tuple[str, ...] = ('command_palette',)
    permissions: tuple[str, ...] = ()
    stats: ExecutionStats = field(default_factory=ExecutionStats)
