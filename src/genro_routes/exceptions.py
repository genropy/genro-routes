# Copyright 2025 Softwell S.r.l. - All Rights Reserved
# SPDX-License-Identifier: Apache-2.0
"""Exceptions for Genro Routes.

This module defines custom exceptions used throughout the routing system.
"""

__all__ = ["NotFound", "NotAuthorized", "UNAUTHORIZED"]

# Sentinel value for unauthorized callable in node() response
UNAUTHORIZED = "--NA--"


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
    """Raised when access to an existing route is denied by filters.

    This exception indicates that the path/selector exists but the current
    filter parameters (e.g., tags) do not allow access to it.

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
