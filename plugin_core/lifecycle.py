from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


LIFECYCLE_EVENTS = (
    'on_install',
    'on_load',
    'on_enable',
    'on_app_ready',
    'on_disable',
    'on_unload',
    'on_uninstall',
)


@dataclass
class LifecycleRegistration:
    event: str
    handler: Callable[..., Any]


def normalize_lifecycle_event(value: str) -> str:
    event = str(value or '').strip()
    if event not in LIFECYCLE_EVENTS:
        raise ValueError(f'不支持的生命周期事件：{event}')
    return event
