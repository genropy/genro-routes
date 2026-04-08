# Copyright 2025-2026 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
