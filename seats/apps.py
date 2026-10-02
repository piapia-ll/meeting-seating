import os

from django.apps import AppConfig


class SeatsConfig(AppConfig):
    name = 'seats'

    def ready(self):
        from . import sync_signals  # noqa: F401

        # The meeting desktop build is deliberately offline and ships without
        # the legacy plugin runtime. Do not initialize that stack at startup.
        if os.environ.get('FUCKSEATS_OFFLINE_ONLY') == '1':
            return

        from .plugin_system import plugin_registry
        plugin_registry.mark_app_ready()
