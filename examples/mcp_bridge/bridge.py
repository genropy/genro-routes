from __future__ import annotations
from typing import Any, Dict, List
from genro_routes import Router

class GenroMCPBridge:
    """Helper to bridge Genro-Routes to Model Context Protocol (MCP)."""
    
    def __init__(self, router: Router):
        self.router = router

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns a list of tools formatted for the Model Context Protocol."""
        # We use the internal introspection to harvest all entries
        nodes = self.router.nodes()
        return self._harvest_tools(nodes)

    def _harvest_tools(self, nodes: Dict[str, Any], path_prefix: str = "") -> List[Dict[str, Any]]:
        tools = []
        
        # Process entries in the current node
        entries = nodes.get("entries", {})
        for name, info in entries.items():
            tool_name = f"{path_prefix}{name}"
            metadata = info.get("metadata", {})
            pydantic_meta = metadata.get("pydantic", {})
            model = pydantic_meta.get("model")
            
            # Build MCP tool definition
            tool = {
                "name": tool_name.replace("/", "_"), # MCP likes flat names with underscores
                "description": info.get("doc", "No description provided"),
                "inputSchema": self._get_schema_from_model(model)
            }
            tools.append(tool)
            
        # Recurse into child routers
        routers = nodes.get("routers", {})
        for r_name, r_nodes in routers.items():
            tools.extend(self._harvest_tools(r_nodes, f"{path_prefix}{r_name}/"))
            
        return tools

    def _get_schema_from_model(self, model: Any) -> Dict[str, Any]:
        """Extracts JSON Schema from a Pydantic model (if available)."""
        if model and hasattr(model, "model_json_schema"):
            return model.model_json_schema()
        return {
            "type": "object",
            "properties": {},
            "description": "No parameter schema available"
        }
