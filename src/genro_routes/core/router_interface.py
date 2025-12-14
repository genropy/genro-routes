# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""RouterInterface - Abstract base for router-like objects.

Defines the minimal interface that all routers must implement.
This allows external packages (like genro-asgi) to create router-compatible
classes without depending on BaseRouter implementation details.

Required methods:
    - get(selector) -> handler or child router or None
    - nodes() -> introspection data dict
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

__all__ = ["RouterInterface"]


class RouterInterface(ABC):
    """Minimal interface for router-like objects.

    Any class implementing this interface can be used where a router is expected,
    enabling duck-typed routing for static files, virtual resources, etc.
    """

    @abstractmethod
    def get(self, selector: str, **options: Any) -> Callable | RouterInterface | None:
        """Resolve selector to handler, child router, or None.

        Args:
            selector: Path to resolve (e.g., "handler_name" or "child/handler").
            **options: Implementation-specific options.

        Returns:
            - Callable handler if selector points to a method/function
            - RouterInterface if selector points to a child router
            - None if not found
        """
        ...

    @abstractmethod
    def nodes(
        self, basepath: str | None = None, lazy: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """Return introspection data for this router.

        Args:
            basepath: Optional path to start from.
            lazy: If True, child data returned as callables.
            **kwargs: Implementation-specific filters.

        Returns:
            Dict with router info, entries, and child routers.
        """
        ...


if __name__ == "__main__":
    pass
