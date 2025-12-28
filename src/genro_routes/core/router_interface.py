# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""RouterInterface - Abstract base for router-like objects.

Defines the minimal interface that all routers must implement.
This allows external packages (like genro-asgi) to create router-compatible
classes without depending on BaseRouter implementation details.

Required methods:
    - node(path) -> RouterNode with best-match resolution
    - nodes() -> introspection data dict
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from genro_routes.core.router_node import RouterNode

__all__ = ["RouterInterface"]


class RouterInterface(ABC):
    """Minimal interface for router-like objects.

    Any class implementing this interface can be used where a router is expected,
    enabling duck-typed routing for static files, virtual resources, etc.

    Attributes:
        name: Router name for identification and debugging.
    """

    name: str | None

    @abstractmethod
    def node(self, path: str, **kwargs: Any) -> RouterNode:
        """Resolve path to a RouterNode using best-match resolution.

        Args:
            path: Path to resolve (e.g., "handler_name" or "child/handler").
            **kwargs: Implementation-specific options (e.g., filter kwargs).

        Returns:
            RouterNode containing entry info if path resolves to a handler,
            or router info if path resolves to a child router.

            The RouterNode is callable for entries. Unconsumed path segments
            are passed as positional arguments when the node is invoked.
        """
        ...

    @abstractmethod
    def nodes(
        self,
        basepath: str | None = None,
        lazy: bool = False,
        mode: str | None = None,
        pattern: str | None = None,
        forbidden: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return introspection data for this router.

        Args:
            basepath: Optional path to start from.
            lazy: If True, child routers returned as references.
            mode: Output format mode (e.g., "openapi"). If None, returns
                  standard introspection format.
            pattern: Regex pattern to filter entry names.
            forbidden: If True, include forbidden entries with reason.
            **kwargs: Implementation-specific filters.

        Returns:
            Dict with router info, entries, and child routers.
        """
        ...


if __name__ == "__main__":
    pass
