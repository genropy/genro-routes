# Live Documentation - genro-routes

**Status**: 🔴 DA REVISIONARE

## The Core Idea

Every genro-routes router can describe itself at runtime:

```python
info = service.api.nodes()           # Structure: entries, child routers
openapi = service.api.nodes(mode="openapi")  # Full OpenAPI 3.0 schema
```

This is **live documentation**: always accurate, machine-readable, queryable.

## Static vs Live Documentation

| Aspect         | Sphinx Autodoc | genro-routes      |
| -------------- | -------------- | ----------------- |
| **When**       | Build time     | Runtime           |
| **Output**     | HTML, PDF      | JSON, OpenAPI     |
| **Accuracy**   | Snapshot       | Always current    |
| **Consumer**   | Humans         | Programs & humans |

**Sphinx** answers: "What **was** the API?"
**genro-routes** answers: "What **is** the API right now?"

## Real-World Application: MCP Bridge

The [mcp_bridge example](../../examples/mcp_bridge/) shows this in action.

The Model Context Protocol (MCP) is how LLMs like Claude discover and call tools.
With genro-routes, **any Python service becomes an MCP tool provider** in ~50 lines:

```python
class GenroMCPBridge:
    def __init__(self, router: Router):
        self.router = router

    def get_mcp_tools(self):
        nodes = self.router.nodes()  # <-- Live introspection
        return self._harvest_tools(nodes)
```

The bridge:

1. **Discovers** all routes via `nodes()`
2. **Extracts** JSON schemas from Pydantic metadata
3. **Generates** MCP-compatible tool definitions

An LLM can then call these tools, with genro-routes handling validation
and routing back to the actual Python functions.

## Why This Matters

Without live documentation, building AI tool servers requires:

- Manual tool definitions
- Duplicate validation logic
- Keeping docs in sync with code

With genro-routes:

- **Discovery** is automatic (`nodes()`)
- **Schemas** come from Pydantic plugin
- **Validation** happens at the router level
- **Documentation** is always current

This is the "missing link" between LLM reasoning and Python execution.

## Other Use Cases

- **API Gateway**: Query microservices for their routes
- **Client Generation**: Build typed clients from live schemas
- **Health Checks**: Verify expected endpoints exist
- **Swagger UI**: Serve OpenAPI directly from the service

## See Also

- [examples/mcp_bridge/](../../examples/mcp_bridge/) - LLM tool integration
- [examples/self_documentation.py](../../examples/self_documentation.py) - Router inspecting itself
- [WHY_GENRO_ROUTES.md](../../examples/WHY_GENRO_ROUTES.md) - The Magic Pattern
