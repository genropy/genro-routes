"""Plugin package for Genro Routes.

This package contains built-in plugins that extend Router functionality.

Available Plugins:
    - ``auth``: Tag-based authorization (AuthPlugin)
    - ``env``: Environment capability-based filtering (EnvPlugin)
    - ``logging``: Handler call logging with timing (LoggingPlugin)
    - ``pydantic``: Input validation via type hints (PydanticPlugin)
    - ``openapi``: OpenAPI schema control (OpenAPIPlugin)

Plugin Registration:
    Plugins self-register when imported. The main ``genro_routes`` package
    imports all built-in plugins automatically.

Creating Custom Plugins:
    Subclass ``BasePlugin`` from ``genro_routes.plugins._base_plugin``::

        from genro_routes.plugins._base_plugin import BasePlugin

        class MyPlugin(BasePlugin):
            plugin_code = "myplugin"
            plugin_description = "My custom plugin"

            def configure(self, enabled: bool = True, option: str = "default"):
                pass  # Storage handled by wrapper

            def wrap_handler(self, router, entry, call_next):
                def wrapper(*args, **kwargs):
                    # Custom logic here
                    return call_next(*args, **kwargs)
                return wrapper

        Router.register_plugin(MyPlugin)

Note:
    Do not import concrete plugins here to keep imports side-effect free.
    Concrete plugin modules self-register when imported via the main package.
"""

__all__: list[str] = []
