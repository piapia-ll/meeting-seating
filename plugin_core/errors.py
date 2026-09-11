class PluginError(Exception):
    """Plugin Core 的基础异常。"""


class PluginNotFoundError(PluginError):
    pass


class PluginDisabledError(PluginError):
    pass


class PluginActionNotFoundError(PluginError):
    pass


class PluginMethodNotAllowedError(PluginError):
    pass


class PluginCompatibilityError(PluginError):
    pass


class PluginPermissionError(PluginError):
    pass


class PluginDependencyError(PluginCompatibilityError):
    pass


class PluginManifestError(PluginError):
    pass
