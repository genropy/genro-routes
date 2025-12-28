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
]


class NotFound(Exception):
    """Raised when a requested route or entry does not exist.

    This exception indicates that the path/selector points to something
    that doesn't exist in the router hierarchy.

    Attributes:
        selector: The selector in format "router_name:path" or just "router_name".
    """

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(f"Entry '{selector}' not found")


class NotAuthorized(Exception):
    """Raised when access to an existing route is denied by filters (403).

    This exception indicates that the path/selector exists and authentication
    tags were provided, but they do not match the entry's requirements.

    Attributes:
        selector: The selector in format "router_name:path" or just "router_name".
    """

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(f"Access to '{selector}' denied")


class NotAuthenticated(Exception):
    """Raised when authentication is required but not provided (401).

    This exception indicates that the path/selector exists and requires
    authentication tags, but none were provided in the request.

    Attributes:
        selector: The selector in format "router_name:path" or just "router_name".
    """

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(f"Authentication required for '{selector}'")


class NotAvailable(Exception):
    """Raised when a required capability is not available (501).

    This exception indicates that the path/selector exists but requires
    capabilities that are not present in the system.

    Attributes:
        selector: The selector in format "router_name:path" or just "router_name".
    """

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(f"Capability not available for '{selector}'")
