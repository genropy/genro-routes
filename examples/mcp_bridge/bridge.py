from __future__ import annotations

from typing import Any

from genro_routes import Router


class GenroMCPBridge:
    """Helper to bridge Genro-Routes to Model Context Protocol (MCP)."""

    def __init__(self, router: Router):
        self.router = router

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        """Returns a list of tools formatted for the Model Context Protocol."""
        # We use the internal introspection to harvest all entries
        nodes = self.router.nodes()
        return self._harvest_tools(nodes)

    def _harvest_tools(self, nodes: dict[str, Any], path_prefix: str = "") -> list[dict[str, Any]]:
        tools = []

        # Process entries in the current node
        entries = nodes.get("entries", {})
        for name, info in entries.items():
            tool_name = f"{path_prefix}{name}"

            # Build MCP tool definition. Both schemas come from the neutral
            # node blocks (params/result), fetched once by genro-routes; the
            # bridge never re-inspects the handler callable.
            tool = {
                "name": tool_name.replace("/", "_"), # MCP likes flat names with underscores
                "description": info.get("doc", "No description provided"),
                "inputSchema": self._input_schema(info),
            }

            # Add response schema if available
            output_schema = (info.get("result") or {}).get("schema")
            if output_schema:
                tool["outputSchema"] = output_schema

            tools.append(tool)

        # Recurse into child routers
        routers = nodes.get("routers", {})
        for r_name, r_nodes in routers.items():
            tools.extend(self._harvest_tools(r_nodes, f"{path_prefix}{r_name}/"))

        return tools

    def _input_schema(self, info: dict[str, Any]) -> dict[str, Any]:
        """Extract the input JSON Schema from the neutral params block."""
        schema = (info.get("params") or {}).get("schema")
        if schema:
            return schema
        return {
            "type": "object",
            "properties": {},
            "description": "No parameter schema available"
        }
