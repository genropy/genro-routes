"""RouterNode - Wrapper for router node information.

RouterNode wraps the result of node() calls, providing a callable interface
to invoke handlers directly and access node metadata.

Example::

    node = router.node("my_handler")
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
    from .base_router import BaseRouter

__all__ = ["RouterNode"]


class RouterNode:
    """Wrapper for router node information with callable interface.

    RouterNode wraps the result of _find_candidate_node() and provides:
    - Direct attribute access to node properties
    - __call__ for invoking entry handlers
    - Proper exception handling for unauthorized/not found cases
    - Customizable exception mapping via errors parameter

    Attributes:
        path: Full path to this node
        error: Error code (None if ok, else "not_found", "not_authenticated", etc.)
        doc: Entry docstring
        metadata: Entry metadata dict

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
        "_partial",
        "_partial_kwargs",
        "_extra_args",
    )

    def __init__(
        self,
        router: BaseRouter,
        errors: dict[str, type[Exception]] | None = None,
        *,
        entry_name: str | None = None,
        path: str | None = None,
        partial: list[str] | None = None,
    ) -> None:
        """Initialize RouterNode.

        Args:
            router: Reference to the router.
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
        self._partial: list[str] = partial if partial is not None else []
        self._partial_kwargs: dict[str, str] = {}
        self._extra_args: list[str] = []

        entry = router._entries.get(entry_name or router.default_entry)
        if entry and self._assign_partial(entry):
            self._entry = entry

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

    def _assign_partial(self, entry: Any) -> bool:
        """Assign partial path values to kwargs and extra_args.

        Returns:
            True if entry can accept the partial args, False otherwise.
        """
        if not self._partial:
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

        for i, value in enumerate(self._partial):
            if i < len(param_names):
                self._partial_kwargs[param_names[i]] = value
            else:
                self._extra_args.append(value)

        # If extra args but no *args in signature, not valid
        return not (self._extra_args and not has_var_positional)

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
            selector = f"{self._router.name}:{path}" if path else self._router.name
            raise exc_class(selector)

        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in self._partial_kwargs}
        merged_kwargs = {**self._partial_kwargs, **filtered_kwargs}
        all_args = (*self._extra_args, *args)

        try:
            return self._entry.handler(*all_args, **merged_kwargs)  # type: ignore[attr-defined, union-attr]
        except Exception as e:
            if ValidationError is not None and isinstance(e, ValidationError):
                custom_exc = self._exceptions.get("validation_error")
                if custom_exc is not None and custom_exc is not ValidationError:
                    selector = f"{self._router.name}:{path}" if path else self._router.name
                    raise custom_exc(selector) from e
            raise

    def to_dict(self) -> dict[str, Any]:
        """Return node data as dict."""
        return {
            "path": self.path,
            "partial": self._partial,
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
        return f"RouterNode(path={self.path!r})"
