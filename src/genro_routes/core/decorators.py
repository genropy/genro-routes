"""Decorator helpers for marking routed methods.

This module contains only marker helpers; no router mutation happens at
decoration time.

``route(*, name=None, endpoint_id=None, **kwargs)``
    Returns a decorator storing metadata on the function under
    ``_route_decorator_kw`` as a list of dicts. All markers belong to the
    class's single router (one router per RoutingClass).

    - Explicit logical name: if ``name`` is provided, the payload sets
      ``entry_name`` to that value. Otherwise the handler name defaults to
      the function name.
    - Extra ``**kwargs`` are copied verbatim into the payload (e.g. plugin flags).
    - Stacking the decorator registers the same function under multiple
      entry names (aliases).
    - The decorator returns the original function unchanged aside from the marker.

Re-exports
----------
This module re-exports ``RoutingClass`` and ``Router`` for convenience so user
code can import everything from one place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .router import Router
from .routing import RoutingClass

__all__ = ["route", "RoutingClass", "Router"]


def route(
    *,
    name: str | None = None,
    endpoint_id: str | None = None,
    **kwargs: Any,
) -> Callable[[Callable], Callable]:
    """Mark a bound method for inclusion in the class's router.

    Args:
        name: Optional explicit entry name (overrides function name/prefix stripping).
        endpoint_id: Optional globally unique identifier for reverse lookup.
            When set, the handler can be resolved via ``router.node("@endpoint_id")``.
        **kwargs: Extra metadata merged into handler entry (e.g. plugin flags).

    Returns:
        Decorator that marks the function for the router.

    Example::

        class Table(RoutingClass):
            @route()
            def list_users(self):
                return ["alice", "bob"]

            @route(name="custom_name", logging_enabled=False)
            def get_user(self, user_id):
                return {"id": user_id}
    """

    def decorator(func: Callable) -> Callable:
        markers = list(getattr(func, "_route_decorator_kw", []))
        payload: dict[str, Any] = {}
        if name is not None:
            payload["entry_name"] = name
        if endpoint_id is not None:
            payload["endpoint_id"] = endpoint_id
        for key, value in kwargs.items():
            payload[key] = value
        markers.append(payload)
        setattr(func, "_route_decorator_kw", markers)  # noqa: B010
        return func

    return decorator
