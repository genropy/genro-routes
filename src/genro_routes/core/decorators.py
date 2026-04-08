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
    router: str | None = None,
    *,
    name: str | None = None,
    endpoint_id: str | None = None,
    **kwargs: Any,
) -> Callable[[Callable], Callable]:
    """Mark a bound method for inclusion in the given router.

    Args:
        router: Router identifier (e.g. ``"api"``). If None, uses the default
            router (only works if the class has exactly one router).
        name: Optional explicit entry name (overrides function name/prefix stripping).
        endpoint_id: Optional globally unique identifier for reverse lookup.
            When set, the handler can be resolved via ``router.node("@endpoint_id")``.
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

        # With single router - @route() works without arguments:
        class Table(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")  # single router

            @route()  # Uses the only router automatically
            def add(self, data):
                ...

        # With multiple routers - must specify:
        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.admin = Router(self, name="admin")

            @route("api")  # Must specify router name
            def public(self):
                ...
    """

    def decorator(func: Callable) -> Callable:
        markers = list(getattr(func, "_route_decorator_kw", []))
        payload: dict[str, Any] = {"name": router}  # None means "use default_router"
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
