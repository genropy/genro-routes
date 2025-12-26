# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AuthPlugin - Authorization plugin with tag-based access control.

This plugin provides tag-based authorization for router entries. It evaluates
authorization rules defined on endpoints against user tags.

Usage::

    from genro_routes import Router, RoutingClass, route

    class MyAPI(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api", auth_rule="admin&internal")
        def admin_action(self):
            return "admin only"

        @route("api", auth_rule="public")
        def public_action(self):
            return "public"

    # Query with user's tags (comma-separated list of tags the user has)
    obj = MyAPI()
    obj.api.node("admin_action", auth_tags="admin,internal")  # user has both tags
    obj.api.nodes(auth_tags="admin")           # user has admin tag
    obj.api.nodes(auth_tags="admin,public")    # user has admin AND public tags

Rule syntax (on entry auth_rule):
    - ``|`` : OR (user must have at least one)
    - ``&`` : AND (user must have all)
    - ``!`` : NOT (user must not have)
    - ``()`` : grouping

NOTE: Comma is NOT allowed in auth_rule. Use ``|`` for OR, ``&`` for AND.
      Comma in auth_tags means the user has multiple tags (always AND).

Example: auth_rule="admin|manager" means "user must have admin OR manager"
Example: auth_rule="admin&!guest" means "user must have admin AND NOT guest"
"""

from __future__ import annotations

from typing import Any

from genro_toolbox import tags_match

from genro_routes.core.router import Router
from genro_routes.core.router_interface import RouterInterface

from ._base_plugin import BasePlugin, MethodEntry

__all__ = ["AuthPlugin"]


class AuthPlugin(BasePlugin):
    """Authorization plugin with tag-based access control."""

    plugin_code = "auth"
    plugin_description = "Authorization plugin with tag-based access control"

    def configure(
        self,
        *,
        rule: str = "",
        enabled: bool = True,
        _target: str = "_all_",
        flags: str | None = None,
    ) -> None:
        """Define authorization rule for this entry/router.

        Args:
            rule: Boolean rule expression (e.g., "admin&internal", "!guest").
                  Use ``|`` for OR, ``&`` for AND. Comma is not allowed.
            enabled: Whether the plugin is enabled (default True)
            _target: Internal - target bucket name
            flags: Internal - flag string

        Raises:
            ValueError: If rule contains comma (use ``|`` for OR instead).
        """
        if "," in rule:
            raise ValueError(
                f"Comma not allowed in auth_rule: {rule!r}. "
                "Use '|' for OR (e.g., 'admin|manager') or '&' for AND (e.g., 'admin&hr')."
            )
        pass  # Storage handled by wrapper

    def allow_entry(
        self, entry: MethodEntry | RouterInterface, **filters: Any
    ) -> str:
        """Filter entries based on authorization rule.

        Args:
            entry: MethodEntry or Router being checked.
            **filters: May contain ``tags`` with user's tags.

        Returns:
            "": Access allowed (entry has no rule, or tags match).
            "not_authenticated": Entry requires tags but none provided.
            "not_authorized": Tags provided but don't match rule.
        """
        if isinstance(entry, RouterInterface):
            results = [self.allow_entry(n, **filters) for n in entry.values()]
            if any(r == "" for r in results):
                return ""
            return results[0] if results else ""

        config = self.configuration(entry.name)
        entry_rule = config.get("rule", "")

        if not entry_rule:
            return ""

        user_tags = filters.get("tags")

        if not user_tags:
            return "not_authenticated"

        tags_set = {v.strip() for v in user_tags.split(",") if v.strip()}

        if tags_match(entry_rule, tags_set):
            return ""

        return "not_authorized"


Router.register_plugin(AuthPlugin)
