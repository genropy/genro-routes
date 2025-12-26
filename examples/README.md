# Faker Service Examples

This directory contains examples of how to wrap libraries using `genro-routes` to create structured, validated, and self-documenting services.

> [!TIP]
> **New to Genro-Routes?** Read [Why wrap a library with Genro-Routes?](./WHY_GENRO_ROUTES.md) to understand the architectural benefits.

## Examples

### 1. Standard Faker (`faker_standard.py`)
Demonstrates explicit routing using the `@route` decorator. Recommended for well-defined APIs.

### 2. Magic Faker (`faker_magic.py`)
Demonstrates dynamic registration and Python introspection to automatically map an entire library.

### 3. Syntax Highlighting (`pygments_highlighting.py`)
Wraps the **Pygments** library. Shows how a complex utility can be turned into a service that consumes code and returns formatted results (HTML/ANSI), with Pydantic validating all formatting options.

### 4. QR Code Generator (`qrcode_generator.py`)
Wraps the **qrcode** library. Perfect example of "Asset Generation as a Service", where input parameters are strictly validated before expensive image processing.

### 5. Authentication & Roles (`auth_roles.py`)
Shows how to use the `AuthPlugin` to protect endpoints with role-based access control.

### 6. Service Composition (`service_composition.py`)
Demonstrates building large apps by composing multiple independent modules into a single hierarchy.

### 7. Self-Documentation (`self_documentation.py`)
A meta-example where **genro-routes documents itself**.

### 8. MCP Bridge (`mcp_bridge/`)
A conceptual implementation of a **Model Context Protocol (MCP)** bridge.

### 9. Repository Explorer (`repo_explorer.py`)
Exposes a repository as a service with `list_dir`, `read_file`, and `get_info` methods. Demonstrates the correct pattern: methods with path parameters instead of one-router-per-file.

> **Evolution ideas**: content caching, full-text search, file watch for changes.

### 10. Deep Repo Explorer (`deep_repo_explorer.py`)
Maps Python files as routers, introspecting classes and functions at runtime. Combined with MCP Bridge, allows an LLM to discover API structure without filesystem access.

> **Evolution ideas**: signature indexing, pattern-based search, semantic search via embeddings.

## Running the Examples

Ensure you have `faker` installed:
```bash
pip install faker
```

Then run the examples directly:
```bash
python faker_standard.py
python faker_magic.py
```

## Why this matters?
These examples show how `genro-routes` can transform a simple utility library into a professional **Service** with:
- **Consistent Interface**: Path-based access.
- **Security**: Plugin-based access control (Auth/Env).
- **Quality**: Automatic schema validation (Pydantic).
- **Communication**: Instant OpenAPI documentation.
