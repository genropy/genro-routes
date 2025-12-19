"""Genro Routes - Instance-scoped routing engine for Python.

Public API surface providing hierarchical handler organization, per-instance
plugin application, and complex service composition through descriptors.

Public exports:
    - ``Router``: Main router class for binding methods to selectors
    - ``RoutingClass``: Mixin for classes that expose routers
    - ``route``: Decorator for marking methods as route handlers

Plugin registration happens lazily via ``import_module`` to avoid cycles.
Built-in plugins (logging, pydantic) are auto-registered on first import.

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

__version__ = "0.10.0"

from .core import Router, RouterInterface, RoutingClass, RoutingContext, route
from .exceptions import UNAUTHORIZED, NotAuthorized, NotFound

# Import plugins to trigger auto-registration (lazy to avoid cycles)
for _plugin in ("logging", "pydantic", "auth", "openapi"):
    import_module(f"{__name__}.plugins.{_plugin}")
del _plugin

__all__ = [
    "Router",
    "RouterInterface",
    "RoutingClass",
    "RoutingContext",
    "route",
    "NotFound",
    "NotAuthorized",
    "UNAUTHORIZED",
]
