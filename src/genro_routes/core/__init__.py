"""Core runtime aggregator for Genro Routes.

Exposes the runtime building blocks from a single module:
``BaseRouter``, ``Router``, ``route``, ``RoutingClass``.

Public API:
    - ``BaseRouter``: Plugin-free routing engine
    - ``Router``: Plugin-enabled router with middleware support
    - ``route``: Decorator for marking handler methods
    - ``RoutingClass``: Mixin for classes exposing routers

Importing this module performs only imports; it does not register plugins
or instantiate routers.
"""

from .base_router import BaseRouter
from .context import RoutingContext
from .decorators import route
from .router import Router
from .router_interface import RouterInterface
from .routing import RoutingClass, is_result_wrapper

__all__ = [
    "BaseRouter",
    "Router",
    "RouterInterface",
    "RoutingContext",
    "is_result_wrapper",
    "route",
    "RoutingClass",
]
