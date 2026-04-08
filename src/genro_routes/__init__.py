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

"""Genro Routes - Instance-scoped routing engine for Python.

Public API surface providing hierarchical handler organization, per-instance
plugin application, and complex service composition through descriptors.

Public exports:
    - ``Router``: Main router class for binding methods to selectors
    - ``RouterNode``: Wrapper returned by node() for handler access
    - ``RoutingClass``: Mixin for classes that expose routers
    - ``route``: Decorator for marking methods as route handlers

Plugin registration happens lazily via ``import_module`` to avoid cycles.
Built-in plugins (logging, pydantic, auth, env, openapi, channel) are
auto-registered on first import.

Example::

    from genro_routes import Router, RoutingClass, route

    class MyService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def hello(self):
            return "Hello, World!"
"""

from importlib import import_module
from importlib.metadata import version as get_version

__version__ = get_version("genro-routes")

from .core import (
    Router,
    RouterInterface,
    RoutingClass,
    RoutingContext,
    is_result_wrapper,
    route,
)
from .core.router_node import RouterNode
from .exceptions import (
    NotAuthenticated,
    NotAuthorized,
    NotAvailable,
    NotFound,
)

# Import plugins to trigger auto-registration (lazy to avoid cycles)
for _plugin in ("logging", "pydantic", "auth", "env", "openapi", "channel"):
    import_module(f"{__name__}.plugins.{_plugin}")
del _plugin

__all__ = [
    "Router",
    "RouterInterface",
    "RouterNode",
    "RoutingClass",
    "RoutingContext",
    "is_result_wrapper",
    "route",
    "NotFound",
    "NotAuthorized",
    "NotAuthenticated",
    "NotAvailable",
]
