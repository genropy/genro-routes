"""Genro Routes - Instance-scoped routing engine for Python.

Public API surface providing hierarchical handler organization, per-instance
plugin application, and service composition by attaching instances. Every
``RoutingClass`` owns exactly one ``Router``, exposed as the lazy ``route``
property.

Public exports:
    - ``Router``: Router class (created by RoutingClass, not by user code)
    - ``RouterInterface``: Abstract interface shared by routers
    - ``RouterNode``: Wrapper returned by node() for handler access
    - ``RoutingClass``: Mixin binding a class to its single router
    - ``RoutingContext``: Execution context with parent-chain lookup
    - ``Section``: Empty RoutingClass used as grouping node
    - ``route``: Decorator for marking methods as route handlers
    - ``is_result_wrapper``: Predicate for ResultWrapper instances
    - Exceptions: ``NotFound``, ``NotAuthorized``, ``NotAuthenticated``,
      ``NotAvailable``

Plugin registration happens lazily via ``import_module`` to avoid cycles.
Built-in plugins (logging, pydantic, auth, env, openapi, channel) are
auto-registered on first import.

Example::

    from genro_routes import RoutingClass, route

    class MyService(RoutingClass):
        @route()
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
    Section,
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
    "Section",
    "is_result_wrapper",
    "route",
    "NotFound",
    "NotAuthorized",
    "NotAuthenticated",
    "NotAvailable",
]
