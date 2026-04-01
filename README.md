# Genro Routes

<p align="center">
  <img src="assets/logo.png" alt="Genro Routes Logo" width="200"/>
</p>

[![PyPI version](https://img.shields.io/pypi/v/genro-routes?cacheSeconds=300)](https://pypi.org/project/genro-routes/)
[![Tests](https://github.com/genropy/genro-routes/actions/workflows/test.yml/badge.svg)](https://github.com/genropy/genro-routes/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/genropy/genro-routes/branch/main/graph/badge.svg)](https://codecov.io/gh/genropy/genro-routes)
[![Documentation](https://readthedocs.org/projects/genro-routes/badge/?version=latest)](https://genro-routes.readthedocs.io/en/latest/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Genro Routes** is a **transport-agnostic routing engine** that decouples method routing from how those methods are exposed. Define your handlers once, then expose them via HTTP, CLI, WebSocket, or any other transport layer.

The routing logic lives in your application objects - the transport adapter (like [genro-asgi](https://github.com/genropy/genro-asgi) for HTTP) simply maps external requests to router entries.

## Why Transport-Agnostic?

Traditional web frameworks tightly couple routing to HTTP. Genro Routes separates these concerns:

| Layer | Responsibility |
|-------|---------------|
| **genro-routes** | Method registration, hierarchies, plugins, introspection |
| **Transport adapter** | Protocol handling, request/response mapping |

This separation enables:

- **Same handlers, multiple transports** - Expose your API via HTTP and CLI without duplication
- **Runtime introspection** - Query available routes, generate documentation, build admin UIs
- **Testability** - Test business logic without HTTP overhead
- **Flexibility** - Swap transports without changing application code

## Use Cases

- **HTTP APIs** - Via [genro-asgi](https://github.com/genropy/genro-asgi) adapter
- **CLI tools** - Via the built-in `RoutingCli` adapter (see below)
- **Internal services** - Direct method invocation with plugin pipeline
- **Admin dashboards** - Runtime introspection for dynamic UIs

## Key Features

1. **Instance-scoped routers** - Each object instantiates its own routers (`Router(self, ...)`) with isolated state.
2. **Friendly registration** - `@route(...)` accepts explicit names, auto-strips prefixes, and supports custom metadata.
3. **Simple hierarchies** - `attach_instance(child, name="alias")` connects RoutingClass instances with path access (`parent.api.node("child/method")`).
4. **Plugin pipeline** - `BasePlugin` provides `on_decore`/`wrap_handler` hooks and plugins inherit from parents automatically.
5. **Runtime configuration** - `routing.configure()` applies global or per-handler overrides with wildcards and returns reports (`"?"`).
6. **Built-in plugins** - `logging`, `pydantic`, `auth`, `env`, `openapi`, and `channel` plugins are included out of the box.
7. **Response schema generation** - Return type annotations (TypedDict, dataclass, etc.) are automatically converted to JSON Schema and exposed in route metadata for bridges to consume.
8. **Full coverage** - The package ships with a comprehensive test suite and no hidden compatibility layers.

## Quick Example

```python
from genro_routes import RoutingClass, Router, route

class OrdersAPI(RoutingClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="orders")

    @route("orders")
    def list(self):
        return ["order-1", "order-2"]

    @route("orders")
    def retrieve(self, ident: str):
        return f"{self.label}:{ident}"

    @route("orders")
    def create(self, payload: dict):
        return {"status": "created", **payload}

orders = OrdersAPI("acme")
print(orders.api.node("list")())        # ["order-1", "order-2"]
print(orders.api.node("retrieve")("42"))  # acme:42

overview = orders.api.nodes()
print(overview["entries"].keys())      # dict_keys(['list', 'retrieve', 'create'])
```

## Hierarchical Routing

Build nested service structures with path access:

```python
class UsersAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list(self):
        return ["alice", "bob"]

class Application(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.users = UsersAPI()

        # Attach child service
        self.api.attach_instance(self.users, name="users")

app = Application()
print(app.api.node("users/list")())  # ["alice", "bob"]

# Introspect hierarchy
info = app.api.nodes()
print(info["routers"].keys())  # dict_keys(['users'])
```

## Learn by Example

We provide a comprehensive gallery of examples in the [examples/](https://github.com/genropy/genro-routes/tree/main/examples) directory:

- **[Standard Faker](https://github.com/genropy/genro-routes/blob/main/examples/faker_standard.py)** - Explicit routing and Pydantic validation.
- **[Magic Faker](https://github.com/genropy/genro-routes/blob/main/examples/faker_magic.py)** - Dynamic mapping of library methods at runtime.
- **[Syntax Highlighting](https://github.com/genropy/genro-routes/blob/main/examples/pygments_highlighting.py)** - Creating a service wrapper around the Pygments library.
- **[Auth & Roles](https://github.com/genropy/genro-routes/blob/main/examples/auth_roles.py)** - Implementing role-based access control.
- **[Service Composition](https://github.com/genropy/genro-routes/blob/main/examples/service_composition.py)** - Building complex apps from independent modules.

Read our guide on **[Why wrap a library with Genro-Routes?](https://github.com/genropy/genro-routes/blob/main/examples/WHY_GENRO_ROUTES.md)** for more specialized insights.

## CLI Adapter

Expose any RoutingClass as a full-featured command-line tool with tab completion, help, and typed parameters — automatically generated from router introspection.

```bash
pip install genro-routes[cli]
```

```python
#!/usr/bin/env python
from genro_routes.cli import RoutingCli
from myapp import OrdersAPI

cli = RoutingCli(OrdersAPI("acme"))
cli.run()
```

```bash
$ myapp list                        # call handler directly
["order-1", "order-2"]

$ myapp retrieve 42                 # positional arguments
acme:42

$ myapp --help                      # auto-generated help
Usage: myapp [OPTIONS] COMMAND [ARGS]...

Commands:
  create    Create a new order.
  list      List all orders.
  retrieve  Retrieve a single order.

$ myapp retrieve --help             # per-command help with types
Usage: myapp retrieve [OPTIONS] IDENT

Arguments:
  IDENT  (str)
```

Features:

- **Routers become command groups** - Multiple routers create nested subcommands
- **Parameters from signatures** - Type hints map to click types (int, bool flags, Choice for Literal/Enum, multiple for list)
- **Tab completion** - Native bash/zsh/fish via click (`eval "$(_MYAPP_COMPLETE=bash_source myapp)"`)
- **Output formatting** - Auto (JSON for dicts, plain for strings), or force `json`/`table`/`raw`
- **Accepts class or instance** - `RoutingCli(MyClass)` or `RoutingCli(MyClass(config=cfg))`

## Installation

```bash
pip install genro-routes
```

With CLI support:

```bash
pip install genro-routes[cli]
```

For development:

```bash
git clone https://github.com/genropy/genro-routes.git
cd genro-routes
pip install -e ".[all]"
```

## Typed Response Schemas

Annotate return types to generate response schemas automatically. Bridges (MCP, OpenAPI) can expose them without extra work:

```python
from typing import TypedDict
from genro_routes import RoutingClass, Router, route

class UserResponse(TypedDict):
    id: int
    name: str
    active: bool

class UsersAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("pydantic")

    @route("api")
    def get_user(self, user_id: int) -> UserResponse:
        return {"id": user_id, "name": "alice", "active": True}

api = UsersAPI()

# Response schema is available in route metadata
entry = api.api._entries["get_user"]
schema = entry.metadata["pydantic"]["response_schema"]
# {"type": "object", "properties": {"id": {"type": "integer"}, ...}}

# OpenAPI translation includes it automatically
openapi = api.api.nodes(mode="openapi")
# paths["/get_user"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
```

Supported types: `TypedDict`, `dict[str, int]`, `list[...]`, `str`, `int`, `bool`, and any type Pydantic can serialize.

## Core Concepts

- **`Router`** - Runtime router bound directly to an object via `Router(self, name="api")`
- **`@route("name")`** - Decorator that marks bound methods for the router with the matching name
- **`RoutingClass`** - Mixin that tracks routers per instance and exposes the `routing` proxy
- **`RoutingContext`** - Extensible execution context with parent chain delegation. Attach any attribute (`ctx.db`, `ctx.user`, `ctx.session`); missing lookups walk up `RoutingContext(parent=...)`. Stored in a `_ctx` slot on each instance — children inherit via `_routing_parent` chain. See [Execution Context Guide](docs/guide/context.md).
- **`BasePlugin`** - Base class for creating plugins with `on_decore` and `wrap_handler` hooks
- **`obj.routing`** - Proxy exposed by every RoutingClass that provides helpers like `get_router(...)` and `configure(...)` for managing routers/plugins without polluting the instance namespace.
- **`RouterNode`** - Callable wrapper returned by `node()`, with `path`, `error`, `doc`, `metadata` properties.
- **`NotFound` / `NotAuthenticated` / `NotAuthorized` / `NotAvailable`** - Exceptions for routing errors (not found, auth required, auth denied, capabilities missing)

## One Name Per Operation

Genro Routes uses **unique names** for handlers rather than overloading the same path with different HTTP methods. Each entry is an **operation** (`list_orders`, `create_order`, `approve_order`), not a resource acted upon by a verb.

This matches how modern API paradigms work: GraphQL, gRPC, tRPC, and MCP all identify operations by name, not by HTTP method. The HTTP verb is inferred automatically at the transport layer (e.g., genro-asgi) when generating OpenAPI schemas or mapping to HTTP endpoints.

See [Why One Name Per Operation](docs/guide/why-one-name-per-operation.md) for the full rationale.

## Pattern Highlights

- **Explicit naming + prefixes** - `@route("api", name="detail")` and `Router(self, prefix="handle_")` separate method names from public route names.
- **Explicit instance hierarchies** - `self.api.attach_instance(self.child, name="alias")` connects RoutingClass instances with parent tracking and auto-detachment.
- **Branch routers** - `Router(self, branch=True)` creates pure organizational nodes without handlers.
- **Built-in and custom plugins** - `Router(self, ...).plug("logging")`, `Router(self, ...).plug("pydantic")`, or custom plugins.
- **Shorthand plugin syntax** - `@route("api", auth="admin")` instead of `@route("api", auth_rule="admin")`. Plugins declare their default parameter via `plugin_default_param`.
- **Channel filtering** - `@route("api", channel="mcp,bot_.*")` controls which transport channels can access each handler. Supports regex patterns.
- **Runtime configuration** - `routing.configure("api:logging/_all_", enabled=False)` applies targeted overrides with wildcards or batch updates.
- **Lazy binding** - Routers auto-bind on first use; no explicit `bind()` call needed.

## Documentation

- **[Full Documentation](https://genro-routes.readthedocs.io/)** - Complete guides, tutorials, and API reference
- **[Quick Start](docs/quickstart.md)** - Get started in 5 minutes
- **[Execution Context](docs/guide/context.md)** - RoutingContext, parent chain, slot-based ctx
- **[FAQ](docs/FAQ.md)** - Common questions and answers

## Testing

Genro Routes ships with a comprehensive test suite:

```bash
PYTHONPATH=src pytest --cov=src/genro_routes --cov-report=term-missing
```

All examples in documentation are verified by the test suite.

## Repository Structure

```text
genro-routes/
├── src/genro_routes/
│   ├── __init__.py          # Public API exports
│   ├── exceptions.py        # NotFound, NotAuthorized, NotAuthenticated, NotAvailable
│   ├── core/                # Core router implementation
│   │   ├── base_router.py   # BaseRouter (plugin-free runtime)
│   │   ├── router.py        # Router (with plugin support)
│   │   ├── router_node.py   # RouterNode (callable wrapper from node())
│   │   ├── router_interface.py  # RouterInterface (abstract base)
│   │   ├── context.py       # RoutingContext (extensible execution context)
│   │   ├── decorators.py    # @route decorator
│   │   └── routing.py       # RoutingClass, ResultWrapper
│   ├── cli/                 # CLI transport adapter
│   │   ├── __init__.py      # RoutingCli (public API)
│   │   ├── _builder.py      # CliBuilder (click tree from nodes())
│   │   ├── _type_map.py     # ParamConverter (Python → click types)
│   │   └── _formatters.py   # OutputFormatter (JSON/table/raw)
│   └── plugins/             # Built-in plugins
│       ├── _base_plugin.py  # BasePlugin, MethodEntry
│       ├── logging.py       # LoggingPlugin
│       ├── pydantic.py      # PydanticPlugin
│       ├── auth.py          # AuthPlugin
│       ├── env.py           # EnvPlugin (+ CapabilitiesSet)
│       ├── openapi.py       # OpenAPIPlugin (+ OpenAPITranslator)
│       └── channel.py       # ChannelPlugin (channel-based filtering)
├── examples/                # Example applications
├── tests/                   # Comprehensive test suite
└── docs/                    # Documentation (Sphinx)
```

## Project Status

Genro Routes is currently in **beta**. The core API is stable with complete documentation.

- **Python Support**: 3.10, 3.11, 3.12, 3.13
- **License**: Apache 2.0

## Current Limitations

- **Instance methods only** - Routers assume decorated functions are bound methods (no static/class method or free function support)
- **Minimal plugin system** - Intentionally simple; advanced features must be added manually

## Roadmap

- **[genro-asgi](https://github.com/genropy/genro-asgi)** - ASGI adapter for HTTP exposure (in development)
- Additional plugins (async, storage, audit trail, metrics)
- Example applications and use cases

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Origin

This project was originally developed as "smartroute" under MIT license and has been renamed and relicensed.
