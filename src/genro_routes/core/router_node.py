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

import inspect
from typing import TYPE_CHECKING, Any

from genro_routes.exceptions import (
    NotAuthenticated,
    NotAuthorized,
    NotAvailable,
    NotFound,
)

try:
    from pydantic import ValidationError
except ImportError:  # pragma: no cover
    ValidationError = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:  # pragma: no cover
    from .router_interface import RouterInterface

__all__ = ["RouterNode"]


class RouterNode:
    """Wrapper for router node information with callable interface.

    RouterNode wraps the dict returned by _find_candidate_node() and provides:
    - Direct attribute access to node properties
    - __call__ for invoking entry handlers
    - __bool__ for checking if node exists
    - Proper exception handling for unauthorized/not found cases
    - Customizable exception mapping via errors parameter

    Attributes:
        type: Node type ("entry", "router", or "root")
        name: Node name
        path: Full path to this node
        error: Error code (None if ok, else "not_found", "not_authenticated", etc.)
        doc: Entry docstring
        metadata: Entry metadata dict
        partial: Raw partial path segments from resolution
        partial_kwargs: Dict mapping parameter names to values from path
        extra_args: List of path segments beyond named parameters (for *args handlers)

    Class Attributes:
        ERROR_CODES: Set of error codes that can be mapped to custom exceptions.
        DEFAULT_EXCEPTIONS: Default exception classes for each error code.
    """

    ERROR_CODES: set[str] = {
        "not_found",
        "not_authorized",
        "not_authenticated",
        "not_available",
        "validation_error",
    }

    DEFAULT_EXCEPTIONS: dict[str, type[Exception]] = {
        "not_found": NotFound,
        "not_authorized": NotAuthorized,
        "not_authenticated": NotAuthenticated,
        "not_available": NotAvailable,
    }
    if ValidationError is not None:
        DEFAULT_EXCEPTIONS["validation_error"] = ValidationError

    __slots__ = (
        "_router",
        "_entry",
        "_entry_name",
        "_exceptions",
        "error",
        "path",
        "partial",
        "partial_kwargs",
        "extra_args",
    )

    def __init__(
        self,
        router: RouterInterface | None = None,
        errors: dict[str, type[Exception]] | None = None,
        *,
        entry_name: str | None = None,
        path: str | None = None,
        partial: list[str] | None = None,
    ) -> None:
        """Initialize RouterNode.

        Args:
            router: Optional reference to the router (for context).
            errors: Optional dict mapping error codes to custom exception classes.
                    Available codes: 'not_found', 'not_authorized', 'not_authenticated',
                    'validation_error'. Custom exceptions override the defaults.
            entry_name: Name of the entry to resolve (if this is an entry node).
            path: Full path to this node.
            partial: Path segments not yet resolved.

        Example::

            node = RouterNode(router, errors={
                'not_found': HTTPNotFound,
                'not_authorized': HTTPForbidden,
            }, entry_name='index')
        """
        self._router = router
        self._entry_name: str | None = entry_name
        self._entry = None

        self._exceptions: dict[str, type[Exception]] = dict(self.DEFAULT_EXCEPTIONS)
        if errors:
            self._exceptions.update(errors)

        self.error: str | None = None

        self.path: str | None = path
        self.partial: list[str] = partial if partial is not None else []
        self.partial_kwargs: dict[str, str] = {}
        self.extra_args: list[str] = []

    def __bool__(self) -> bool:
        """Return True if this node exists (has a router)."""
        return self._router is not None

    @property
    def doc(self) -> str:
        """Return entry docstring."""
        if self._entry is None:
            return ""
        return inspect.getdoc(self._entry.func) or self._entry.func.__doc__ or ""

    @property
    def metadata(self) -> dict[str, Any]:
        """Return entry metadata (only meta_* kwargs from @route decorator)."""
        if self._entry is None:
            return {}
        return dict(self._entry.metadata.get("meta", {}))

    @property
    def is_entry(self) -> bool:
        """Return True if this is an entry node."""
        return self._entry_name is not None

    @property
    def is_callable(self) -> bool:
        """Return True if this node can be called without error."""
        return self.error is None and self._entry is not None

    @property
    def valid_entry(self) -> bool:
        """Return True if this node has a valid entry."""
        return self._entry is not None

    def set_entry(self, entry_name: str) -> None:
        """Set entry by name if it exists and accepts partial args."""
        entry = self._router._entries.get(entry_name)  # type: ignore[union-attr]
        if not entry or not self._assign_partial(entry):
            return
        self._entry = entry
        self._entry_name = entry_name

    def _assign_partial(self, entry: Any) -> bool:
        """Assign partial path values to kwargs and extra_args.

        Returns:
            True if entry can accept the partial args, False otherwise.
        """
        if not self.partial:
            return True

        sig = inspect.signature(entry.func)

        param_names = [
            name
            for name, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]

        has_var_positional = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL
            for p in sig.parameters.values()
        )

        for i, value in enumerate(self.partial):
            if i < len(param_names):
                self.partial_kwargs[param_names[i]] = value
            else:
                self.extra_args.append(value)

        # If extra args but no *args in signature, not valid
        return not (self.extra_args and not has_var_positional)

    def set_custom_exceptions(
        self, errors: dict[str, type[Exception]] | None
    ) -> RouterNode:
        """Set custom exception classes for error codes.

        Args:
            errors: Dict mapping error codes to exception classes.

        Returns:
            self (for chaining).
        """
        if errors:
            self._exceptions.update(errors)
        return self

    def check_valid(self, **kwargs: Any) -> RouterNode:
        """Check validity via router's _allow_entry and set error if not allowed.

        Args:
            **kwargs: Plugin-prefixed filter kwargs (e.g., auth_tags="admin").

        Returns:
            self (for chaining). Sets self.error if validation fails.
        """
        if not self._entry or not self._router:
            return self
        result = self._router._allow_entry(self._entry, **kwargs)  # type: ignore[union-attr, attr-defined]
        if result:
            self.error = result
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the handler if this node has an entry.

        Args:
            *args: Positional arguments passed to the handler.
            **kwargs: Keyword arguments passed to the handler. Note: kwargs that
                conflict with partial_kwargs (from path) are ignored - path wins.

        Returns:
            The result of calling the handler.

        Raises:
            Exception mapped to error code: If error is set (not_found,
                not_authenticated, not_authorized, not_available).
            Exception mapped to 'validation_error': If pydantic validation fails.
        """
        path = self.path or ""

        # Check for error or missing entry
        error_code = self.error or ("not_found" if self._entry is None else None)
        if error_code:
            exc_class = self._exceptions.get(error_code, NotFound)
            raise exc_class(path)

        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in self.partial_kwargs}
        merged_kwargs = {**self.partial_kwargs, **filtered_kwargs}
        all_args = (*self.extra_args, *args)

        try:
            return self._entry.handler(*all_args, **merged_kwargs)  # type: ignore[attr-defined, union-attr]
        except Exception as e:
            if ValidationError is not None and isinstance(e, ValidationError):
                custom_exc = self._exceptions.get("validation_error")
                if custom_exc is not None and custom_exc is not ValidationError:
                    raise custom_exc(path) from e
            raise

    def to_dict(self) -> dict[str, Any]:
        """Return node data as dict."""
        return {
            "is_entry": self.is_entry,
            "path": self.path,
            "partial": self.partial,
        }

    def __eq__(self, other: object) -> bool:
        """Compare RouterNode with another object."""
        if isinstance(other, dict):
            if not self and other == {}:
                return True
            return self.to_dict() == other
        if isinstance(other, RouterNode):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    def __repr__(self) -> str:
        if not self:
            return "RouterNode(empty)"
        return f"RouterNode(is_entry={self.is_entry!r}, path={self.path!r})"
