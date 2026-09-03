# Copyright 2025-2026 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
