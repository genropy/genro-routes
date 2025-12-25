# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""RuleBasedPlugin - Base class for rule-based access control plugins.

This module provides an abstract base for plugins that evaluate boolean rules
against a set of values (tags, capabilities, etc.).

Subclasses must define:
    - ``plugin_code``: unique identifier (e.g., "auth", "allow")
    - ``plugin_description``: human-readable description
    - ``filter_key``: key in filters dict (e.g., "tags", "capabilities")
    - ``no_values_error``: error string when no values provided (e.g., "not_authenticated")
    - ``mismatch_error``: error string when values don't match rule (e.g., "not_authorized")
"""

from __future__ import annotations

from typing import Any

from genro_toolbox import tags_match

from genro_routes.core.router_interface import RouterInterface

from ._base_plugin import BasePlugin, MethodEntry

__all__ = ["RuleBasedPlugin"]


class RuleBasedPlugin(BasePlugin):
    """Base class for plugins that evaluate boolean rules against values.

    Provides common ``configure()`` with comma validation and ``allow_entry()``
    implementation. Subclasses customize behavior via class attributes.
    """

    # Subclasses MUST override these
    filter_key: str = ""  # Key in filters dict (e.g., "tags", "capabilities")
    no_values_error: str = ""  # Error when no values provided
    mismatch_error: str = ""  # Error when values don't match rule

    def configure(  # type: ignore[override]
        self,
        *,
        rule: str = "",
        enabled: bool = True,
        _target: str = "_all_",
        flags: str | None = None,
    ) -> None:
        """Define rule for this entry/router.

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
                f"Comma not allowed in {self.plugin_code}_rule: {rule!r}. "
                "Use '|' for OR (e.g., 'admin|manager') or '&' for AND (e.g., 'admin&hr')."
            )
        pass  # Storage handled by wrapper

    def allow_entry(
        self, entry: MethodEntry | RouterInterface, **filters: Any
    ) -> bool | str:
        """Filter entries based on rule evaluation.

        Args:
            entry: MethodEntry or Router being checked.
            **filters: May contain filter_key with the values to check.

        Returns:
            True: Access allowed (entry has no rule, or values match).
            no_values_error: Entry requires values but none provided.
            mismatch_error: Values provided but they don't match rule.
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

        user_values = filters.get(self.filter_key)

        if not user_values:
            return self.no_values_error

        values_set = {v.strip() for v in user_values.split(",") if v.strip()}

        if tags_match(entry_rule, values_set):
            return True

        return self.mismatch_error

    def on_attached_to_parent(self, parent_plugin: RuleBasedPlugin) -> None:  # type: ignore[override]
        """Rule-based plugins do not inherit configuration from parent."""
        pass
