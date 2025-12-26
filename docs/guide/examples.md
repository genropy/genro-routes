# Examples Gallery

Learning by example is often the fastest way to understand the architectural power of `genro-routes`. This gallery showcases a variety of use cases, from simple library wrappers to complex service compositions.

```{tip}
**New to Genro-Routes?** Read our architectural deep-dive: [Why wrap a library with Genro-Routes?](https://github.com/genropy/genro-routes/blob/main/examples/WHY_GENRO_ROUTES.md)
```

## Library Wrappers

These examples show how to take existing Python libraries and turn them into robust, validated, and self-documenting services.

### 1. Standard Faker
Demonstrates explicit routing using the `{route}` decorator. Perfect for well-defined APIs where you want full control over which methods are exposed.
- **Source**: [examples/faker_standard.py](https://github.com/genropy/genro-routes/blob/main/examples/faker_standard.py)

### 2. Magic Faker (Dynamic Mapping)
Shows how to use Python introspection to automatically map **all public methods** of a library (Faker providers) into the routing tree with zero boilerplate.
- **Source**: [examples/faker_magic.py](https://github.com/genropy/genro-routes/blob/main/examples/faker_magic.py)

### 3. Syntax Highlighting (Pygments)
Turns the **Pygments** library into a service. It demonstrates how Pydantic validation protects complex formatting options (HTML vs ANSI).
- **Source**: [examples/pygments_highlighting.py](https://github.com/genropy/genro-routes/blob/main/examples/pygments_highlighting.py)

### 4. QR Code Generator
A classic "Asset Generation as a Service" example. Shows how to validate input data before triggering expensive image processing.
- **Source**: [examples/qrcode_generator.py](https://github.com/genropy/genro-routes/blob/main/examples/qrcode_generator.py)

## Architectural Patterns

### 5. Authentication & Roles
A deep dive into the `AuthPlugin`. Shows how to protect specific nodes with role tags and how to handle the new specific exceptions like `NotAuthenticated` and `NotAuthorized`.
- **Source**: [examples/auth_roles.py](https://github.com/genropy/genro-routes/blob/main/examples/auth_roles.py)

### 6. Service Composition
One of the most powerful features of the library. Shows how to build a large application by mounting independent `RoutingClass` modules (like "Billing" and "Inventory") into a single, unified hierarchical tree.
- **Source**: [examples/service_composition.py](https://github.com/genropy/genro-routes/blob/main/examples/service_composition.py)

### 7. Self-Documentation (Meta-Example)
The ultimate demonstration of dynamic mapping: **genro-routes documenting itself**. Exposes the internal `Router` API as a service, showing how to use the library as a transparent management layer for existing codebases.
- **Source**: [examples/self_documentation.py](https://github.com/genropy/genro-routes/blob/main/examples/self_documentation.py)

## LLM & MCP Integration

These examples demonstrate how genro-routes enables **live documentation** that LLMs can consume directly, turning any Python service into an AI-accessible tool provider.

### 8. MCP Bridge

A conceptual implementation of a **Model Context Protocol (MCP)** bridge. Shows how to:

- Discover all routes via `nodes()` introspection
- Extract JSON schemas from Pydantic metadata
- Generate MCP-compatible tool definitions
- Route LLM tool calls back to Python functions

Includes an agent simulation using the Anthropic API.

- **Source**: [examples/mcp_bridge/](https://github.com/genropy/genro-routes/blob/main/examples/mcp_bridge/)

### 9. Repository Explorer

Exposes a filesystem repository as a service with `list_dir`, `read_file`, and `get_info` methods. Demonstrates the correct pattern: **methods with path parameters** instead of one-router-per-file (anti-pattern).

- **Source**: [examples/repo_explorer.py](https://github.com/genropy/genro-routes/blob/main/examples/repo_explorer.py)

```{tip}
**Evolution ideas**: content caching, full-text search, file watch for changes.
```

### 10. Deep Repo Explorer

Maps Python files as routers, introspecting classes and functions at runtime. Combined with MCP Bridge, allows an LLM to **discover API structure without filesystem access**.

- **Source**: [examples/deep_repo_explorer.py](https://github.com/genropy/genro-routes/blob/main/examples/deep_repo_explorer.py)

```{tip}
**Evolution ideas**: signature indexing, pattern-based search, semantic search via embeddings.
```

---

## Running the Examples

You can find all these files in the `examples/` directory of the repository. To run them:

1. Clone the repository.
2. Install dependencies: `pip install faker pygments qrcode[pil]`.
3. Run any example directly: `python examples/faker_standard.py`.
