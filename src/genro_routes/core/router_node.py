"""RouterNode - Wrapper for router node information.

RouterNode wraps the result of node() calls, providing a callable interface
to invoke handlers directly and access node metadata.

Example::

    node = router.node("my_handler")
    if node:
        result = node()  # Invoke the handler
        print(node.name, node.metadata)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from genro_routes.exceptions import (
    UNAUTHENTICATED,
    UNAUTHORIZED,
    NotAuthenticated,
    NotAuthorized,
    NotFound,
)

try:
    from pydantic import ValidationError
except ImportError:  # pragma: no cover
    ValidationError = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:  # pragma: no cover
    from .base_router import BaseRouter

__all__ = ["RouterNode"]


class RouterNode:
    """Wrapper for router node information with callable interface.

    RouterNode wraps the dict returned by node() and provides:
    - Direct attribute access to node properties
    - __call__ for invoking entry handlers
    - __bool__ for checking if node exists
    - Proper exception handling for unauthorized/not found cases
    - Customizable exception mapping via errors parameter

    Attributes:
        type: Node type ("entry", "router", or "root")
        name: Node name
        path: Full path to this node
        callable: The handler (for entries) or None
        doc: Entry docstring
        metadata: Entry metadata dict
        description: Router description (for routers)
        owner_doc: Owner class docstring (for routers)
        default_entry: True if this is a default_entry resolution
        partial_kwargs: Dict mapping parameter names to values from path (when partial=True)
        extra_args: List of path segments beyond named parameters (for *args handlers)
        varargs_required: True if extra_args present but handler doesn't accept *args
        openapi: OpenAPI schema (when mode="openapi")

    Class Attributes:
        ERROR_CODES: Set of error codes that can be mapped to custom exceptions.
        DEFAULT_EXCEPTIONS: Default exception classes for each error code.
    """

    # Available error codes for custom exception mapping
    ERROR_CODES: set[str] = {
        "not_found",
        "not_authorized",
        "not_authenticated",
        "validation_error",
    }

    # Default exceptions for each error code
    DEFAULT_EXCEPTIONS: dict[str, type[Exception]] = {
        "not_found": NotFound,
        "not_authorized": NotAuthorized,
        "not_authenticated": NotAuthenticated,
    }
    # Add ValidationError only if pydantic is available
    if ValidationError is not None:
        DEFAULT_EXCEPTIONS["validation_error"] = ValidationError

    __slots__ = (
        "_data",
        "type",
        "name",
        "path",
        "callable",
        "doc",
        "metadata",
        "description",
        "owner_doc",
        "default_entry",
        "partial_kwargs",
        "extra_args",
        "varargs_required",
        "openapi",
        "_router",
        "_exceptions",
    )

    def __init__(
        self,
        data: dict[str, Any],
        router: BaseRouter | None = None,
        errors: dict[str, type[Exception]] | None = None,
    ) -> None:
        """Initialize RouterNode from a dict.

        Args:
            data: Dict containing node information from node().
            router: Optional reference to the router (for context).
            errors: Optional dict mapping error codes to custom exception classes.
                    Available codes: 'not_found', 'not_authorized', 'not_authenticated',
                    'validation_error'. Custom exceptions override the defaults.

        Example::

            node = RouterNode(data, router, errors={
                'not_found': HTTPNotFound,
                'not_authorized': HTTPForbidden,
            })
        """
        self._data = data
        self._router = router

        # Build exception mapping: start with defaults, update with custom
        self._exceptions: dict[str, type[Exception]] = dict(self.DEFAULT_EXCEPTIONS)
        if errors:
            self._exceptions.update(errors)

        # Extract common fields
        self.type: str | None = data.get("type")
        self.name: str | None = data.get("name")
        self.path: str | None = data.get("path")
        self.callable: Callable | None = data.get("callable")
        self.doc: str = data.get("doc", "")
        self.metadata: dict[str, Any] = data.get("metadata", {})

        # Router-specific fields
        self.description: str | None = data.get("description")
        self.owner_doc: str | None = data.get("owner_doc")

        # Partial resolution fields
        self.default_entry: bool = data.get("default_entry", False)
        self.partial_kwargs: dict[str, str] = data.get("partial_kwargs", {})
        self.extra_args: list[str] = data.get("extra_args", [])
        self.varargs_required: bool = data.get("varargs_required", False)

        # OpenAPI mode field
        self.openapi: dict[str, Any] | None = data.get("openapi")

    def __bool__(self) -> bool:
        """Return True if this node exists (has a type)."""
        return self.type is not None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the handler if this node has a callable.

        Works for entry nodes and root nodes with a default_entry.

        Args:
            *args: Positional arguments passed to the handler.
            **kwargs: Keyword arguments passed to the handler. Note: kwargs that
                conflict with partial_kwargs (from path) are ignored - path wins.

        Returns:
            The result of calling the handler.

        Raises:
            Exception mapped to 'not_found': If this node has no callable
                (router without default_entry, root without default_entry),
                or varargs_required is True.
            Exception mapped to 'not_authorized': If the callable is UNAUTHORIZED sentinel.
            Exception mapped to 'validation_error': If pydantic validation fails.
        """
        path = self.path or ""
        router_name = self._router.name if self._router else None

        if self.callable is None:
            exc_class = self._exceptions.get("not_found", NotFound)
            raise exc_class(path, router_name)

        if self.callable is UNAUTHENTICATED:
            exc_class = self._exceptions.get("not_authenticated", NotAuthenticated)
            raise exc_class(path, router_name)

        if self.callable is UNAUTHORIZED:
            exc_class = self._exceptions.get("not_authorized", NotAuthorized)
            raise exc_class(path, router_name)

        # If extra_args present but function doesn't accept *args, raise not_found
        if self.varargs_required:
            exc_class = self._exceptions.get("not_found", NotFound)
            raise exc_class(path, router_name)

        # Merge partial_kwargs with caller kwargs
        # partial_kwargs (from path) have precedence - filter out conflicts from kwargs
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in self.partial_kwargs}
        merged_kwargs = {**self.partial_kwargs, **filtered_kwargs}

        # Prepend extra_args (if any) to caller args
        all_args = (*self.extra_args, *args)

        # Call the handler, catching ValidationError if mapped
        try:
            return self.callable(*all_args, **merged_kwargs)
        except Exception as e:
            # Check if this is a ValidationError and we have a custom mapping
            if ValidationError is not None and isinstance(e, ValidationError):
                custom_exc = self._exceptions.get("validation_error")
                if custom_exc is not None and custom_exc is not ValidationError:
                    raise custom_exc(path, router_name) from e
            raise

    @property
    def is_entry(self) -> bool:
        """Return True if this is an entry node."""
        return self.type == "entry"

    @property
    def is_router(self) -> bool:
        """Return True if this is a router node."""
        return self.type == "router"

    @property
    def is_root(self) -> bool:
        """Return True if this is a root node (empty path resolution)."""
        return self.type == "root"

    @property
    def is_authorized(self) -> bool:
        """Return True if this entry is authorized (callable is not UNAUTHORIZED or UNAUTHENTICATED)."""
        return self.callable is not UNAUTHORIZED and self.callable is not UNAUTHENTICATED

    def to_dict(self) -> dict[str, Any]:
        """Return the original dict data."""
        return dict(self._data)

    def __eq__(self, other: object) -> bool:
        """Compare RouterNode with another object.

        Special case: an empty RouterNode equals an empty dict.
        Otherwise, compares underlying data dicts.
        """
        if isinstance(other, dict):
            if not self and other == {}:
                return True
            return self._data == other
        if isinstance(other, RouterNode):
            return self._data == other._data
        return NotImplemented

    def __repr__(self) -> str:
        if not self:
            return "RouterNode(empty)"
        return f"RouterNode(type={self.type!r}, name={self.name!r}, path={self.path!r})"
