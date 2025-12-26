# Model Context Protocol (MCP) Bridge

This example demonstrates how **Genro-Routes** can serve as an automated backend for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

By leveraging the library's built-in introspection and plugin system, you can transform any existing Python codebase into a suite of **Tools** that an LLM (like Claude or GPT) can discover, understand, and execute with full type safety.

## How it Works

1.  **Discovery**: The bridge walks the `genro-routes` hierarchy to find all registered handlers.
2.  **Tool Generation**: Each route is converted into an MCP Tool definition.
3.  **Schema Mapping**: The `PydanticPlugin` automatically provides the JSON Schema for the tool's parameters, ensuring the LLM knows exactly what arguments to send.
4.  **Guided Execution**: When the LLM calls a tool, the request is routed back through the `RouterNode`, which validates the inputs before calling the actual Python function.

## File Structure

- **`bridge.py`**: The core logic that translates a Genro Router hierarchy into a list of MCP-compatible tool definitions.
- **`demo.py`**: A simple demonstration that prints the generated JSON schemas for a sample Math service.
- **`agent_sim.py`**: A live simulation script using the Anthropic SDK. It shows a real LLM performing a multi-step task by "calling" the tools exposed via Genro-Routes.

## Getting Started

### 1. Prerequisites
Install the required dependencies:
```bash
pip install genro-routes faker anthropic pydantic
```

### 2. View the Schemas
Run the basic demo to see how Genro-Routes describes your code to an AI:
```bash
python demo.py
```

### 3. Run the LLM Simulation
If you have an Anthropic API key, you can see the agent in action:
```bash
export ANTHROPIC_API_KEY='your_api_key_here'
python agent_sim.py
```

## Why Genro-Routes for AI Agents?

Without a routing engine, building MCP servers requires manual tool definition and repetitive validation logic. **Genro-Routes** removes this boilerplate by treating your code as a structured, navigable tree. 

It provides the "missing link" between the fuzzy world of LLM reasoning and the rigid world of Python execution, providing **Security (Auth/Env)**, **Reliability (Pydantic)**, and **Visibility (OpenAPI/Introspection)** out of the box.
