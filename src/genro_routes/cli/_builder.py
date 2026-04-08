# Copyright 2025-2026 Softwell S.r.l. — Apache License 2.0
"""Builds a click command hierarchy from a RoutingClass instance."""

import asyncio
import enum
import inspect
from typing import Any, get_type_hints

import click

from genro_routes.core.routing import RoutingClass

from ._formatters import OutputFormatter
from ._type_map import ParamConverter


def _cli_name(name: str) -> str:
    """Convert a Python identifier to CLI convention (underscores to hyphens)."""
    return name.replace("_", "-")


class CliBuilder:
    """Generates a click Group/Command tree from router introspection."""

    def __init__(self, instance: RoutingClass, *, output_format: str = "auto"):
        self._instance = instance
        self._formatter = OutputFormatter(output_format)
        self._converter = ParamConverter()

    def build(self, name: str | None = None) -> click.Group:
        """Build the root click.Group from all registered routers."""
        routers = dict(self._instance._iter_registered_routers())
        root_name = name or self._instance.__class__.__name__.lower()
        root_doc = inspect.getdoc(self._instance) or ""

        root = click.Group(name=root_name, help=root_doc)

        if len(routers) == 1:
            # Single router: entries become direct commands on root
            router = next(iter(routers.values()))
            nodes_data = router.nodes()
            self._populate_group(root, nodes_data)
        else:
            # Multiple routers: each becomes a sub-group
            for router_name, router in routers.items():
                nodes_data = router.nodes()
                if not nodes_data:
                    continue
                sub_group = click.Group(
                    name=router_name,
                    help=nodes_data.get("description") or "",
                )
                self._populate_group(sub_group, nodes_data)
                root.add_command(sub_group)

        return root

    def _populate_group(self, group: click.Group, nodes_data: dict[str, Any]) -> None:
        """Add entries as commands and child routers as sub-groups."""
        for entry_name, entry_info in nodes_data.get("entries", {}).items():
            cmd = self._make_command(entry_name, entry_info)
            group.add_command(cmd)

        for child_name, child_data in nodes_data.get("routers", {}).items():
            if not child_data:
                continue
            child_group = click.Group(
                name=child_name,
                help=child_data.get("description") or "",
            )
            self._populate_group(child_group, child_data)
            group.add_command(child_group)

    def _make_command(self, entry_name: str, entry_info: dict[str, Any]) -> click.Command:
        """Create a click.Command from a single entry."""
        handler = entry_info["callable"]
        doc = entry_info.get("doc", "")
        params = self._converter.to_click_params(handler)
        is_async = inspect.iscoroutinefunction(handler)
        formatter = self._formatter
        enum_params = self._enum_param_map(handler)

        def callback(**kwargs: Any) -> None:
            # Convert enum string values back to enum members
            for param_name, enum_type in enum_params.items():
                if param_name in kwargs and isinstance(kwargs[param_name], str):
                    kwargs[param_name] = enum_type[kwargs[param_name]]

            result = asyncio.run(handler(**kwargs)) if is_async else handler(**kwargs)
            output = formatter.format(result)
            if output is not None:
                click.echo(output)

        return click.Command(
            name=_cli_name(entry_name),
            callback=callback,
            params=params,
            help=doc,
        )

    def _enum_param_map(self, handler: Any) -> dict[str, type[enum.Enum]]:
        """Return {param_name: EnumType} for parameters annotated with an Enum."""
        try:
            hints = get_type_hints(handler, include_extras=True)
        except Exception:
            return {}
        hints.pop("return", None)
        return {
            name: hint
            for name, hint in hints.items()
            if isinstance(hint, type) and issubclass(hint, enum.Enum)
        }
