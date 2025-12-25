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

from genro_routes.core.router import Router

from ._rule_based import RuleBasedPlugin

__all__ = ["AuthPlugin"]


class AuthPlugin(RuleBasedPlugin):
    """Authorization plugin with tag-based access control."""

    plugin_code = "auth"
    plugin_description = "Authorization plugin with tag-based access control"

    filter_key = "tags"
    no_values_error = "not_authenticated"
    mismatch_error = "not_authorized"


Router.register_plugin(AuthPlugin)
