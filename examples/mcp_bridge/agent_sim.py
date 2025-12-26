from __future__ import annotations
import os
import json
import anthropic
from genro_routes import Router, RoutingClass, route
from bridge import GenroMCPBridge

# 1. Define the Services (Tools for the LLM)
class MathService(RoutingClass):
    def __init__(self):
        self.router = Router(self, name="math").plug("pydantic")

    @route("math")
    def add(self, a: int, b: int) -> int:
        """Adds two integers together."""
        print(f"[EXECUTING] math/add({a}, {b})")
        return a + b

    @route("math")
    def multiply(self, a: float, b: float) -> float:
        """Multiplies two floating point numbers."""
        print(f"[EXECUTING] math/multiply({a}, {b})")
        return a * b

class RootApp(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.math = MathService()
        self.api.attach_instance(self.math)

# 2. The Agent Simulation
def run_agent_demo():
    # Setup
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: Please set ANTHROPIC_API_KEY environment variable.")
        return

    client = anthropic.Anthropic(api_key=api_key)
    app = RootApp()
    bridge = GenroMCPBridge(app.api)
    
    # Get tools from Genro-Routes
    mcp_tools = bridge.get_mcp_tools()
    
    # Standardize names for the LLM (internal mapping)
    # MCP bridge uses underscores for tool names, we need to map them back to /
    tool_map = {t['name']: t['name'].replace("_", "/") for t in mcp_tools}

    print("--- LLM Agent Simulation via Genro-Routes ---")
    prompt = "Add 15 and 27, then multiply the result by 2. Tell me the final answer."
    print(f"Prompt: {prompt}\n")

    # Call the LLM
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1024,
        tools=[{
            "name": t['name'],
            "description": t['description'],
            "input_schema": t['inputSchema']
        } for t in mcp_tools],
        messages=[{"role": "user", "content": prompt}]
    )

    # Process Tool Calls (Loop for multi-step reasoning)
    current_messages = [{"role": "user", "content": prompt}]
    
    while message.stop_reason == "tool_use":
        # Add the assistant message with tool_use to history
        current_messages.append({"role": "assistant", "content": message.content})
        
        tool_results = []
        for block in message.content:
            if block.type == "tool_use":
                tool_id = block.id
                tool_name = block.name
                tool_input = block.input
                
                # ROUTE the call back to Genro-Routes!
                genro_path = tool_map[tool_name]
                print(f"[AGENT] Calling {genro_path} with {tool_input}")
                
                result = app.api.node(genro_path)(**tool_input)
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result)
                })
        
        # Send results back to the LLM
        current_messages.append({"role": "user", "content": tool_results})
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1024,
            tools=[{
                "name": t['name'],
                "description": t['description'],
                "input_schema": t['inputSchema']
            } for t in mcp_tools],
            messages=current_messages
        )

    print("\n[FINAL RESPONSE]")
    print(message.content[0].text)

if __name__ == "__main__":
    run_agent_demo()
