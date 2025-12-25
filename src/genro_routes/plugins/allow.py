# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AllowPlugin - Capability-based access control plugin.

This plugin provides capability-based filtering for router entries. It evaluates
capability requirements defined on endpoints against system capabilities.

Capabilities can come from two sources:

1. **Request capabilities**: Passed explicitly via ``allow_capabilities`` parameter
2. **Instance capabilities**: Declared on RoutingClass instances via the
   ``capabilities`` property

When traversing a router hierarchy, capabilities are **accumulated** from all
RoutingClass instances along the path. This allows child services to inherit
capabilities from their parents while adding their own.

Usage::

    from genro_routes import Router, RoutingClass, route

    class MyAPI(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("allow")
            self.capabilities = {"redis"}  # This instance provides redis

        @route("api", allow_rule="pyjwt&redis")
        def create_jwt(self):
            return "jwt created"

        @route("api", allow_rule="paypal|stripe")
        def process_payment(self):
            return "payment processed"

    # Query with additional request capabilities
    obj = MyAPI()
    obj.api.node("create_jwt", allow_capabilities="pyjwt")  # OK: pyjwt from request + redis from instance
    obj.api.node("create_jwt")  # not_available: only redis from instance, missing pyjwt

    # Dynamic capabilities via property override
    class PaymentService(RoutingClass):
        @property
        def capabilities(self) -> set[str]:
            caps = set()
            if self._stripe_configured:
                caps.add("stripe")
            return caps

Rule syntax (on entry allow_rule):
    - ``|`` : OR (system must have at least one)
    - ``&`` : AND (system must have all)
    - ``!`` : NOT (system must not have)
    - ``()`` : grouping

NOTE: Comma is NOT allowed in allow_rule. Use ``|`` for OR, ``&`` for AND.
      Comma in allow_capabilities means the system has multiple capabilities.

Example: allow_rule="pyjwt&redis" means "system must have pyjwt AND redis"
Example: allow_rule="paypal|stripe" means "system must have paypal OR stripe"
"""

from __future__ import annotations

from typing import Any

from genro_toolbox import tags_match

from genro_routes.core.router import Router
from genro_routes.core.router_interface import RouterInterface
from genro_routes.plugins._base_plugin import MethodEntry

from ._rule_based import RuleBasedPlugin

__all__ = ["AllowPlugin"]


class AllowPlugin(RuleBasedPlugin):
    """Capability-based access control plugin.

    Accumulates capabilities from RoutingClass instances along the
    router hierarchy, combining them with request capabilities.
    """

    plugin_code = "allow"
    plugin_description = "Capability-based access control plugin"

    filter_key = "capabilities"
    no_values_error = "not_available"
    mismatch_error = "not_available"

    def allow_entry(
        self, entry: MethodEntry | RouterInterface, **filters: Any
    ) -> bool | str:
        """Filter entries based on capability requirements.

        Capabilities are accumulated from:
        1. Router capabilities (``router_capabilities`` if pre-computed, else from router)
        2. Request capabilities (``capabilities`` parameter)

        The combined set is checked against the entry's ``allow_rule``.

        Args:
            entry: MethodEntry or Router being checked.
            **filters: May contain ``router_capabilities`` (pre-computed) and/or
                      ``capabilities`` (from request).

        Returns:
            True: Access allowed (entry has no rule, or capabilities match).
            "not_available": Entry requires capabilities but none available,
                           or capabilities don't match rule.
        """
        if isinstance(entry, RouterInterface):
            results = [self.allow_entry(n, **filters) for n in entry.values()]
            if any(r is True for r in results):
                return True
            return results[0] if results else True

        config = self.configuration(entry.name)
        entry_rule = config.get("rule", "")

        if not entry_rule:
            return True

        # Use pre-computed router capabilities or compute them
        router_caps = filters.get("router_capabilities")
        if router_caps is None:
            router_caps = self._router.current_capabilities

        # Parse request capabilities
        request_caps_str = filters.get(self.filter_key)
        request_caps: set[str] = set()
        if request_caps_str:
            request_caps = {v.strip() for v in request_caps_str.split(",") if v.strip()}

        # Combine all capabilities
        all_caps = router_caps | request_caps

        if not all_caps:
            return self.no_values_error

        if tags_match(entry_rule, all_caps):
            return True

        return self.mismatch_error


Router.register_plugin(AllowPlugin)
