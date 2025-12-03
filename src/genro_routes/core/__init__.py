"""Core runtime aggregator for Genro Routes.

Exposes the runtime building blocks from a single module:
``BaseRouter``, ``Router``, ``route``, ``RoutedClass``.

Public API:
    - ``BaseRouter``: Plugin-free routing engine
    - ``Router``: Plugin-enabled router with middleware support
    - ``route``: Decorator for marking handler methods
    - ``RoutedClass``: Mixin for classes exposing routers

Importing this module performs only imports; it does not register plugins
or instantiate routers.
"""

from .base_router import BaseRouter
from .decorators import route
from .routed import RoutedClass
from .router import Router

__all__ = [
    "BaseRouter",
    "Router",
    "route",
    "RoutedClass",
]
