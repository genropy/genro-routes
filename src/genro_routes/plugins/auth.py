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

        @route("api", auth_tags="admin,internal")
        def admin_action(self):
            return "admin only"

        @route("api", auth_tags="public")
        def public_action(self):
            return "public"

    # Filter by tags
    obj = MyAPI()
    obj.api.nodes(tags="admin")           # entries with 'admin' tag
    obj.api.nodes(tags="admin,public")    # OR: admin OR public
    obj.api.nodes(tags="admin&internal")  # AND: admin AND internal
    obj.api.nodes(tags="!admin")          # NOT: not admin
    obj.api.nodes(tags="(admin|public)&!internal")  # complex expression

Operators:
    - ``,`` or ``|`` : OR
    - ``&`` : AND
    - ``!`` : NOT
    - ``()`` : grouping
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

    def configure(  # type: ignore[override]
        self,
        *,
        tags: str = "",
        enabled: bool = True,
        _target: str = "_all_",
        flags: str | None = None,
    ) -> None:
        """Define authorization tags for this entry/router.

        Args:
            tags: Comma-separated tag names (e.g., "admin,internal")
            enabled: Whether authorization is enabled (default True)
            _target: Internal - target bucket name
            flags: Internal - flag string
        """
        pass  # Storage handled by wrapper

    def on_attached_to_parent(self, parent_plugin: BasePlugin) -> None:
        """Merge parent tags with child tags (union).

        AuthPlugin uses union semantics: parent tags are combined with
        child tags, not replaced. This allows hierarchical tag inheritance
        where a parent router's tags apply to all children.

        Example:
            parent._all_.tags = "corporate"
            child._all_.tags = "internal"
            → child._all_.tags effective = "corporate,internal"
        """
        # Let base class handle common config (enabled, etc.)
        super().on_attached_to_parent(parent_plugin)

        # Store original child tags for later delta calculations
        my_tags_str = self.configuration().get("tags", "")
        self._own_tags = {t.strip() for t in my_tags_str.split(",") if t.strip()}

        # Then handle tags with union semantics
        parent_tags_str = parent_plugin.configuration().get("tags", "")
        parent_tags = {t.strip() for t in parent_tags_str.split(",") if t.strip()}

        merged = parent_tags | self._own_tags
        if merged:
            self.configure(tags=",".join(sorted(merged)))

    def on_parent_config_changed(
        self, _old_config: dict[str, Any], new_config: dict[str, Any]
    ) -> None:
        """Propagate parent tag changes with union semantics.

        When parent tags change, recalculate child's effective tags:
        - Remove old parent tags
        - Add new parent tags
        - Keep child's own tags

        Example:
            parent: "corporate" → "corporate,hr"
            child own: "internal"
            child effective: "corporate,internal" → "corporate,hr,internal"
        """
        new_parent_tags_str = new_config.get("tags", "")
        new_parent_tags = {t.strip() for t in new_parent_tags_str.split(",") if t.strip()}

        # Get child's own tags (stored at attach time)
        own_tags: set[str] = getattr(self, "_own_tags", set())

        # Calculate new effective tags: own + new parent
        new_effective = own_tags | new_parent_tags

        if new_effective:
            self.configure(tags=",".join(sorted(new_effective)))
        else:
            self.configure(tags="")

    def allow_node(self, node: MethodEntry | RouterInterface, **filters: Any) -> bool:
        """Filter nodes (entries or routers) based on tag expression.

        Args:
            node: MethodEntry or Router being checked.
            **filters: Must contain 'tags' key with the filter expression.

        Returns:
            True if node matches (or has matching children), False otherwise.
        """
        rule = filters.get("tags")
        if not rule:
            return True
        if isinstance(node, RouterInterface):
            return any(self.allow_node(n, **filters) for n in node.values())
        # MethodEntry - read from configuration
        config = self.configuration(node.name)
        tags_str = config.get("tags", "")
        entry_tags = {t.strip() for t in tags_str.split(",") if t.strip()}
        return bool(tags_match(rule, entry_tags))


Router.register_plugin(AuthPlugin)
