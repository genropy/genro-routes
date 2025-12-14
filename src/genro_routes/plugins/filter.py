# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""FilterPlugin - Filter entries by tags with boolean expressions.

This plugin allows tagging router entries and filtering them using
boolean expressions with AND, OR, and NOT operators.

Usage::

    from genro_routes import Router

    class MyAPI:
        api = Router()
        api.plug("filter")

        @api.route(filter_tags="admin,internal")
        def admin_action(self):
            return "admin only"

        @api.route(filter_tags="public")
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

import re
from typing import Any

from genro_routes.core.router import Router
from genro_routes.core.router_interface import RouterInterface

from ._base_plugin import BasePlugin, MethodEntry

__all__ = ["FilterPlugin"]


class FilterPlugin(BasePlugin):
    """Filter entries by tags with boolean expressions."""

    plugin_code = "filter"
    plugin_description = "Filter entries by tags with boolean expressions"

    def configure(  # type: ignore[override]
        self, *, tags: str = "", _target: str = "_all_", flags: str | None = None
    ) -> None:
        """Define tags for this entry/router.

        Args:
            tags: Comma-separated tag names (e.g., "admin,internal")
            _target: Internal - target bucket name
            flags: Internal - flag string
        """
        pass  # Storage handled by wrapper

    def on_attached_to_parent(self, parent_plugin: BasePlugin) -> None:
        """Merge parent tags with child tags (union).

        FilterPlugin uses union semantics: parent tags are combined with
        child tags, not replaced. This allows hierarchical tag inheritance
        where a parent router's tags apply to all children.

        Example:
            parent._all_.tags = "corporate"
            child._all_.tags = "internal"
            → child._all_.tags effective = "corporate,internal"
        """
        # Let base class handle common config (enabled, etc.)
        super().on_attached_to_parent(parent_plugin)

        # Then handle tags with union semantics
        parent_tags_str = parent_plugin.configuration().get("tags", "")
        my_tags_str = self.configuration().get("tags", "")

        parent_tags = {t.strip() for t in parent_tags_str.split(",") if t.strip()}
        my_tags = {t.strip() for t in my_tags_str.split(",") if t.strip()}

        merged = parent_tags | my_tags
        if merged:
            self.configure(tags=",".join(sorted(merged)))

    def allow_node(
        self, node: MethodEntry | RouterInterface, **filters: Any
    ) -> bool:
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
        return self._match_tags(rule, entry_tags)

    def _match_tags(self, rule: str, entry_tags: set[str]) -> bool:
        """Evaluate tag expression against entry's tags.

        Args:
            rule: Boolean expression (e.g., "admin+public", "!internal")
            entry_tags: Set of tags assigned to the entry.

        Returns:
            True if expression matches, False otherwise.

        Raises:
            ValueError: If rule syntax is invalid.
        """
        # Single regex with named groups for operators, NOT+tag, and tags
        pattern = r"(?P<op>[&,|])|!(?P<not>[a-zA-Z_]\w*)|(?P<tag>[a-zA-Z_]\w*)"
        op_map = {"&": "&", ",": "|", "|": "|"}

        def replace_token(m: re.Match[str]) -> str:
            if m.group("op"):
                return op_map[m.group("op")]
            if m.group("not"):
                return "!1" if m.group("not") in entry_tags else "!0"
            return "1" if m.group("tag") in entry_tags else "0"

        expr = re.sub(pattern, replace_token, rule)

        # Validate: only 0, 1, !, &, |, (, )
        if not re.fullmatch(r"[01!&|()]+", expr):
            raise ValueError(f"Invalid tag rule: {rule}")

        # Check max 6 nesting levels
        if re.search(r"\({7}", expr):
            raise ValueError(f"Tag rule too deeply nested (max 6): {rule}")

        # Convert to Python boolean expression
        py_map = {"!": " not ", "&": " and ", "|": " or ", "0": " False ", "1": " True "}
        expr = re.sub(r"[!&|01]", lambda m: py_map[m.group()], expr)

        return bool(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307


Router.register_plugin(FilterPlugin)
