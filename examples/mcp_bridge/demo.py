from __future__ import annotations
import json
from genro_routes import Router, RoutingClass, route
from bridge import GenroMCPBridge

# 1. Define a sample library (e.g., a simple calculator)
class MathService(RoutingClass):
    def __init__(self):
        # We use Pydantic for the bridge to see the type hints
        self.router = Router(self, name="math").plug("pydantic")

    @route("math")
    def add(self, a: int, b: int) -> int:
        """Adds two integers together."""
        return a + b

    @route("math")
    def multiply(self, a: float, b: float) -> float:
        """Multiplies two floating point numbers."""
        return a * b

class RootApp(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.math = MathService()
        self.api.attach_instance(self.math)

# 2. Run the Demo
if __name__ == "__main__":
    app = RootApp()
    bridge = GenroMCPBridge(app.api)
    
    print("--- Genro-Routes to MCP Bridge Demo ---")
    
    # Generate the MCP tools
    tools = bridge.get_mcp_tools()
    
    print(f"\nDiscovered {len(tools)} tools for the LLM:")
    
    for tool in tools:
        print(f"\n[Tool: {tool['name']}]")
        print(f"Description: {tool['description']}")
        print(f"Schema: {json.dumps(tool['inputSchema'], indent=2)}")

    print("\n--- VISION ---")
    print("An actual MCP server would just take this JSON list and expose it")
    print("via stdio or HTTP. The LLM then receives perfect definitions")
    print("of your Python library automatically.")
