# Copyright 2025 Softwell S.r.l. - All Rights Reserved
# SPDX-License-Identifier: Apache-2.0
"""Exceptions for Genro Routes.

This module defines custom exceptions used throughout the routing system.
"""

__all__ = [
    "NotFound",
    "NotAuthorized",
    "NotAuthenticated",
    "NotAvailable",
    "UNAUTHORIZED",
    "UNAUTHENTICATED",
    "NOT_AVAILABLE",
]

# Sentinel value for unauthorized callable in node() response (403)
UNAUTHORIZED = "--NA--"

# Sentinel value for unauthenticated callable in node() response (401)
UNAUTHENTICATED = "--401--"

# Sentinel value for capability not available in node() response (501)
NOT_AVAILABLE = "--501--"


class NotFound(Exception):
    """Raised when a requested route or entry does not exist.

    This exception indicates that the path/selector points to something
    that doesn't exist in the router hierarchy.

    Attributes:
        selector: The path that was not found.
        router_name: The router where the lookup failed.
    """

    def __init__(self, selector: str, router_name: str | None = None) -> None:
        self.selector = selector
        self.router_name = router_name
        if router_name:
            message = f"Entry '{selector}' not found in router '{router_name}'"
        else:
            message = f"Entry '{selector}' not found"
        super().__init__(message)


class NotAuthorized(Exception):
    """Raised when access to an existing route is denied by filters (403).

    This exception indicates that the path/selector exists and authentication
    tags were provided, but they do not match the entry's requirements.

    Attributes:
        selector: The path that was denied.
        router_name: The router where access was denied.
    """

    def __init__(self, selector: str, router_name: str | None = None) -> None:
        self.selector = selector
        self.router_name = router_name
        if router_name:
            message = f"Access to '{selector}' denied in router '{router_name}'"
        else:
            message = f"Access to '{selector}' denied"
        super().__init__(message)


class NotAuthenticated(Exception):
    """Raised when authentication is required but not provided (401).

    This exception indicates that the path/selector exists and requires
    authentication tags, but none were provided in the request.

    Attributes:
        selector: The path that requires authentication.
        router_name: The router where authentication is required.
    """

    def __init__(self, selector: str, router_name: str | None = None) -> None:
        self.selector = selector
        self.router_name = router_name
        if router_name:
            message = f"Authentication required for '{selector}' in router '{router_name}'"
        else:
            message = f"Authentication required for '{selector}'"
        super().__init__(message)


class NotAvailable(Exception):
    """Raised when a required capability is not available (501).

    This exception indicates that the path/selector exists but requires
    capabilities that are not present in the system.

    Attributes:
        selector: The path that requires capabilities.
        router_name: The router where capabilities are required.
    """

    def __init__(self, selector: str, router_name: str | None = None) -> None:
        self.selector = selector
        self.router_name = router_name
        if router_name:
            message = f"Capability not available for '{selector}' in router '{router_name}'"
        else:
            message = f"Capability not available for '{selector}'"
        super().__init__(message)
