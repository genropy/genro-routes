# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""EnvPlugin - Environment capability-based access control plugin.

This plugin provides capability-based filtering for router entries. It evaluates
capability requirements defined on endpoints against system capabilities.

Capabilities can come from two sources:

1. **Request capabilities**: Passed explicitly via ``env_capabilities`` parameter
2. **Instance capabilities**: Declared on RoutingClass instances via a
   ``CapabilitiesSet`` subclass

When traversing a router hierarchy, capabilities are **accumulated** from all
RoutingClass instances along the path. This allows child services to inherit
capabilities from their parents while adding their own.

Usage::

    from genro_routes import Router, RoutingClass, route
    from genro_routes.plugins.env import CapabilitiesSet, capability

    class MyCapabilities(CapabilitiesSet):
        @capability
        def redis(self) -> bool:
            return True  # Check if redis is available

        @capability
        def pyjwt(self) -> bool:
            return "pyjwt" in sys.modules

    class MyAPI(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("env")
            self.capabilities = MyCapabilities()

        @route("api", env_requires="pyjwt&redis")
        def create_jwt(self):
            return "jwt created"

        @route("api", env_requires="paypal|stripe")
        def process_payment(self):
            return "payment processed"

    # Query with additional request capabilities
    obj = MyAPI()
    obj.api.node("create_jwt", env_capabilities="pyjwt")  # OK: pyjwt from request + redis from instance
    obj.api.node("create_jwt")  # not_available: only redis from instance, missing pyjwt

    # Dynamic capabilities via CapabilitiesSet
    class PaymentCapabilities(CapabilitiesSet):
        def __init__(self, service):
            self._service = service

        @capability
        def stripe(self) -> bool:
            return self._service._stripe_configured

        @capability
        def paypal(self) -> bool:
            return self._service._paypal_configured

    class PaymentService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("env")
            self._stripe_configured = True
            self._paypal_configured = False
            self.capabilities = PaymentCapabilities(self)

Rule syntax (on entry env_requires):
    - ``|`` : OR (system must have at least one)
    - ``&`` : AND (system must have all)
    - ``!`` : NOT (system must not have)
    - ``()`` : grouping

NOTE: Comma is NOT allowed in env_requires. Use ``|`` for OR, ``&`` for AND.
      Comma in env_capabilities means the system has multiple capabilities.

Example: env_requires="pyjwt&redis" means "system must have pyjwt AND redis"
Example: env_requires="paypal|stripe" means "system must have paypal OR stripe"
"""

from __future__ import annotations

from typing import Any

from genro_toolbox import tags_match

from genro_routes.core.router import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry

__all__ = ["EnvPlugin", "CapabilitiesSet", "capability"]


class EnvPlugin(BasePlugin):
    """Environment capability-based access control plugin.

    Accumulates capabilities from RoutingClass instances along the
    router hierarchy, combining them with request capabilities.
    """

    plugin_code = "env"
    plugin_description = "Environment capability-based access control plugin"

    def configure(
        self,
        *,
        requires: str = "",
        enabled: bool = True,
        _target: str = "_all_",
        flags: str | None = None,
    ) -> None:
        """Define capability requirements for this entry/router.

        Args:
            requires: Boolean rule expression (e.g., "pyjwt&redis", "paypal|stripe").
                      Use ``|`` for OR, ``&`` for AND. Comma is not allowed.
            enabled: Whether the plugin is enabled (default True)
            _target: Internal - target bucket name
            flags: Internal - flag string

        Raises:
            ValueError: If requires contains comma (use ``|`` for OR instead).
        """
        if "," in requires:
            raise ValueError(
                f"Comma not allowed in env_requires: {requires!r}. "
                "Use '|' for OR (e.g., 'pyjwt|redis') or '&' for AND (e.g., 'pyjwt&redis')."
            )
        pass  # Storage handled by wrapper

    def deny_reason(self, entry: MethodEntry, **filters: Any) -> str:
        """Filter entries based on capability requirements.

        Capabilities are accumulated from:
        1. Router capabilities (``router_capabilities`` if pre-computed, else from router)
        2. Request capabilities (``capabilities`` parameter)

        The combined set is checked against the entry's ``env_requires``.

        Args:
            entry: MethodEntry being checked.
            **filters: May contain ``router_capabilities`` (pre-computed) and/or
                      ``capabilities`` (from request).

        Returns:
            "": Access allowed (no reason to deny).
            "not_available": Entry requires capabilities but none available,
                           or capabilities don't match rule.
        """
        config = self.configuration(entry.name)
        entry_rule = config.get("requires", "")

        if not entry_rule:
            return ""

        # Use pre-computed router capabilities or compute them
        router_caps = filters.get("router_capabilities")
        if router_caps is None:
            router_caps = self._router.current_capabilities

        # Parse request capabilities
        request_caps_str = filters.get("capabilities")
        request_caps: set[str] = set()
        if request_caps_str:
            request_caps = {v.strip() for v in request_caps_str.split(",") if v.strip()}

        # Combine all capabilities
        all_caps = router_caps | request_caps

        if not all_caps:
            return "not_available"

        if tags_match(entry_rule, all_caps):
            return ""

        return "not_available"


# ---------------------------------------------------------------------------
# CapabilitiesSet - Dynamic capability container
# ---------------------------------------------------------------------------


def capability(func):
    """Mark a method as a capability checker.

    The decorated method should return a bool indicating whether the capability
    is currently active.

    Usage::

        class ServerCapabilities(CapabilitiesSet):
            @capability
            def jwt(self) -> bool:
                return "jwt" in sys.modules

            @capability
            def redis(self) -> bool:
                return self._redis_client is not None
    """
    func._is_capability = True
    return func


class CapabilitiesSet:
    """Base class for dynamic capability sets.

    Subclasses define capabilities as methods decorated with ``@capability``.
    The class behaves like a set: supports ``in``, ``len``, and iteration.

    Capabilities are evaluated dynamically on each access, allowing for
    runtime conditions (e.g., time of day, module availability, configuration).

    Usage::

        from genro_routes.plugins.env import CapabilitiesSet, capability

        class ServerCapabilities(CapabilitiesSet):
            @capability
            def jwt(self) -> bool:
                return "pyjwt" in sys.modules

            @capability
            def send_mail(self) -> bool:
                hour = datetime.now().hour
                return 8 <= hour <= 20

        caps = ServerCapabilities()
        "jwt" in caps       # True if pyjwt is installed
        list(caps)          # ["jwt", "send_mail"] (only active ones)
        len(caps)           # number of active capabilities

    Integration with RoutingClass::

        class MyService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.capabilities = ServerCapabilities()
    """

    def __iter__(self):
        """Yield names of currently active capabilities."""
        for name in dir(self):
            if name.startswith("_"):
                continue
            method = getattr(self, name)
            if callable(method) and getattr(method, "_is_capability", False) and method():
                yield name

    def __contains__(self, item: str) -> bool:
        """Check if a capability is currently active."""
        method = getattr(self, item, None)
        if method and getattr(method, "_is_capability", False):
            return bool(method())
        return False

    def __len__(self) -> int:
        """Return the number of currently active capabilities."""
        return sum(1 for _ in self)


Router.register_plugin(EnvPlugin)
