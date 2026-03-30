# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ChannelPlugin - Channel-based endpoint filtering.

This plugin filters endpoint visibility based on the request channel
(mcp, rest, bot_*, web, etc.). It works alongside AuthPlugin (who) and
EnvPlugin (what's available) to control endpoint access.

Usage::

    from genro_routes import Router, RoutingClass, route

    class MyAPI(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("channel")
            self.api.channel.configure(channels="*")  # default: all channels

        @route("api", channel_channels="mcp")
        def mcp_only(self):
            return "only accessible from MCP channel"

        @route("api", channel_channels="mcp,bot_.*")
        def mcp_and_bots(self):
            return "MCP + any bot channel"

        @route("api")
        def everywhere(self):
            return "inherits * from router config"

    obj = MyAPI()
    obj.api.nodes(channel_channel="mcp")     # sees all three
    obj.api.nodes(channel_channel="rest")    # sees only everywhere
    obj.api.node("mcp_only", channel_channel="mcp")  # OK
    obj.api.node("mcp_only", channel_channel="rest")  # NotAvailable

Channel patterns:
    - Comma-separated list of patterns: ``"mcp,bot_.*,rest"``
    - Each pattern is matched with ``re.fullmatch`` against the request channel
    - ``"*"`` is a special wildcard that matches any channel
    - Empty string means no channels allowed (default closed)
"""

from __future__ import annotations

import re
from typing import Any

from genro_routes.core.router import Router
from genro_routes.core.router_interface import RouterInterface

from ._base_plugin import BasePlugin, MethodEntry

__all__ = ["ChannelPlugin"]


class ChannelPlugin(BasePlugin):
    """Channel-based endpoint filtering plugin.

    Controls access to router entries based on the request channel.
    Channels represent where a request originates from (mcp, rest,
    bot_sourcerer, web, etc.).

    Behavior:
        - **Default closed**: entry without ``channels`` configured
          returns ``"not_available"``
        - **Wildcard**: ``channels="*"`` opens endpoint to all channels
        - **Regex patterns**: comma-separated, matched with ``re.fullmatch``
        - **Config inheritance**: child routers inherit parent channel config

    Attributes:
        plugin_code: "channel" - used for registration and config prefix.
        plugin_description: Human-readable description.
        plugin_default_param: "channels" - enables shorthand syntax.
    """

    plugin_code = "channel"
    plugin_description = "Channel-based endpoint filtering"
    plugin_default_param = "channels"

    def configure(
        self,
        *,
        channels: str = "",
        enabled: bool = True,
        _target: str = "_all_",
        flags: str | None = None,
    ) -> None:
        """Define allowed channels for this entry/router.

        Args:
            channels: Comma-separated list of channel patterns.
                      Each pattern is matched with ``re.fullmatch``.
                      Use ``"*"`` to allow all channels.
                      Empty string means no channels allowed.
            enabled: Whether the plugin is enabled (default True).
            _target: Internal - target bucket name.
            flags: Internal - flag string.
        """
        pass  # Storage handled by wrapper

    def deny_reason(
        self, entry: MethodEntry | RouterInterface, **filters: Any
    ) -> str:
        """Filter entries based on channel.

        Args:
            entry: MethodEntry or Router being checked.
            **filters: May contain ``channel`` with request channel string.

        Returns:
            "": Access allowed (channel matches).
            "not_available": Channel doesn't match or not configured.
        """
        if isinstance(entry, RouterInterface):
            all_nodes = list(entry._entries.values()) + list(entry._children.values())  # type: ignore[attr-defined]
            results = [self.deny_reason(n, **filters) for n in all_nodes]
            if any(r == "" for r in results):
                return ""
            return results[0] if results else ""

        config = self.configuration(entry.name)
        allowed = config.get("channels", "")

        if not allowed:
            return "not_available"

        if allowed.strip() == "*":
            return ""

        request_channel = filters.get("channel", "")
        if not request_channel:
            return "not_available"

        patterns = [p.strip() for p in allowed.split(",") if p.strip()]
        for pattern in patterns:
            if re.fullmatch(pattern, request_channel):
                return ""

        return "not_available"


Router.register_plugin(ChannelPlugin)
