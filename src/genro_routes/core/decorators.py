"""Decorator helpers for marking routed methods.

This module contains only marker helpers; no router mutation happens at
decoration time.

``route(router, *, name=None, **kwargs)``
    Returns a decorator storing metadata on the function under ``_route_decorator_kw``
    as a list of dicts. Each payload starts with ``{"name": router}``.

    - Explicit logical name: if ``name`` is provided, the payload sets ``entry_name``
      to that value. Otherwise the handler name defaults to the function name.
    - Extra ``**kwargs`` are copied verbatim into the payload (e.g. plugin flags).
    - Multiple routers can target the same function by stacking decorators.
    - The decorator returns the original function unchanged aside from the marker.

Re-exports
----------
This module re-exports ``RoutedClass`` and ``Router`` for convenience so user
code can import everything from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .routed import RoutedClass
from .router import Router

__all__ = ["route", "RoutedClass", "Router"]


def route(router: str, *, name: str | None = None, **kwargs: Any) -> Callable[[Callable], Callable]:
    """Mark a bound method for inclusion in the given router.

    Args:
        router: Router identifier (e.g. ``"api"``).
        name: Optional explicit entry name (overrides function name/prefix stripping).
        **kwargs: Extra metadata merged into handler entry (e.g. plugin flags).

    Returns:
        Decorator that marks the function for the specified router.

    Example::

        @route("api")
        def list_users(self):
            return ["alice", "bob"]

        @route("api", name="custom_name", logging_enabled=False)
        def get_user(self, user_id):
            return {"id": user_id}
    """

    def decorator(func: Callable) -> Callable:
        markers = list(getattr(func, "_route_decorator_kw", []))
        payload = {"name": router}
        if name is not None:
            payload["entry_name"] = name
        for key, value in kwargs.items():
            payload[key] = value
        markers.append(payload)
        setattr(func, "_route_decorator_kw", markers)  # noqa: B010
        return func

    return decorator
