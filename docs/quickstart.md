# Quick Start

Get started with Genro Routes in 5 minutes.

Genro Routes is a **transport-agnostic routing engine** - you define your handlers once, then expose them via HTTP (using [genro-asgi](https://github.com/genropy/genro-asgi)), CLI, or any other transport.

## Installation

```bash
pip install genro-routes
```

## Your First Router

Create a service with instance-scoped routing:

```python
from genro_routes import RoutingClass, Router, route

class Service(RoutingClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="api")

    @route("api")
    def describe(self):
        return f"service:{self.label}"

# Each instance is isolated
first = Service("alpha")
second = Service("beta")

assert first.api.node("describe")() == "service:alpha"
assert second.api.node("describe")() == "service:beta"
```

**Key concept**: Routers are instantiated in `__init__` with `Router(self, ...)` - each instance gets its own isolated router.

## Custom Entry Names

<!-- test: test_router_basic.py::test_prefix_and_name_override -->

[From test](https://github.com/genropy/genro-routes/blob/main/tests/test_router_basic.py#L151-L156)

Use prefixes and explicit names for cleaner method registration:

```python
class SubService(RoutingClass):
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.routes = Router(self, name="routes", prefix="handle_")

    @route("routes")
    def handle_list(self):
        return f"{self.prefix}:list"

    @route("routes", name="detail")
    def handle_detail(self, ident: int):
        return f"{self.prefix}:detail:{ident}"

sub = SubService("users")

# Prefix stripped: "handle_list" → "list"
assert sub.routes.node("list")() == "users:list"

# Custom name used: "handle_detail" → "detail"
assert sub.routes.node("detail")(10) == "users:detail:10"
```

## Single Router Default

<!-- test: test_router_basic.py::TestSingleRouterDefault::test_route_without_args_uses_single_router -->

When a class has exactly one router, `@route()` without arguments uses it automatically:

```python
class Table(RoutingClass):
    def __init__(self):
        self.table = Router(self, name="table")

    @route()  # Uses the only router automatically
    def add(self, data):
        return f"added:{data}"

t = Table()
assert t.table.node("add")("x") == "added:x"
```

If the class has multiple routers, you must specify the router name explicitly.

## Building Hierarchies

Create nested router structures:

```python
class RootAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.users = SubService("users")
        self.products = SubService("products")

        self.api.attach_instance(self.users, name="users")
        self.api.attach_instance(self.products, name="products")

root = RootAPI()

# Access with path separator
assert root.api.node("users/list")() == "users:list"
assert root.api.node("products/detail")(5) == "products:detail:5"
```

## Adding Plugins

<!-- test: test_router_basic.py::test_plugins_are_per_instance_and_accessible -->

[From test](https://github.com/genropy/genro-routes/blob/main/tests/test_router_basic.py#L159-L167)

Extend behavior with plugins. Built-in plugins (`logging`, `pydantic`, `auth`, `env`, `openapi`) are pre-registered.

```python
class PluginService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("logging")

    @route("api")
    def do_work(self):
        return "ok"

svc = PluginService()
result = svc.api.node("do_work")()  # Automatically logged
```

## Validating Arguments

<!-- test: test_pydantic_plugin.py::test_pydantic_plugin_accepts_valid_input -->

[From test](https://github.com/genropy/genro-routes/blob/main/tests/test_pydantic_plugin.py#L22-L27)

Use Pydantic for automatic validation:

```python
class ValidateService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("pydantic")

    @route("api")
    def concat(self, text: str, number: int = 1) -> str:
        return f"{text}:{number}"

svc = ValidateService()

# Valid inputs
assert svc.api.node("concat")("hello", 3) == "hello:3"
assert svc.api.node("concat")("hi") == "hi:1"

# Invalid inputs raise ValidationError
# svc.api.node("concat")(123, "oops")  # ValidationError!
```

## Response Schemas

Return type annotations are automatically converted to JSON Schema. This enables bridges (MCP, OpenAPI) to expose typed response contracts:

```python
from typing import TypedDict

class StatusResponse(TypedDict):
    ok: bool
    message: str

class HealthService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("pydantic")

    @route("api")
    def health(self) -> StatusResponse:
        return {"ok": True, "message": "running"}

svc = HealthService()

# Response schema is generated automatically
entry = svc.api._entries["health"]
schema = entry.metadata["pydantic"]["response_schema"]
# {"type": "object", "properties": {"ok": {"type": "boolean"}, "message": {"type": "string"}}, ...}
```

Supported types: `TypedDict`, `dict[str, T]`, `list[T]`, `str`, `int`, `bool`, and any type Pydantic can serialize. TypedDict requires Python 3.12+.

## Execution Context

Handlers need access to shared state (database, user, session) without
knowing which adapter provides it. Use `RoutingContext`:

```python
from genro_routes import RoutingClass, RoutingContext, Router, route

class OrderService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list_orders(self):
        return self.ctx.db.query("SELECT * FROM orders")

# Create a context and set it
ctx = RoutingContext()
ctx.db = my_database

svc = OrderService()
svc.ctx = ctx
svc.api.node("list_orders")()  # handler reads self.ctx.db
```

Contexts can be layered with `RoutingContext(parent=parent_ctx)` — missing
attributes walk up the chain. The context is stored in a `_ctx` slot and
walks up the `_routing_parent` chain — children inherit it automatically.

See the **[Execution Context Guide](guide/context.md)** for the full reference.

## Next Steps

Now that you've learned the basics:

- **[Basic Usage Guide](guide/basic-usage.md)** - Detailed explanation of core concepts
- **[Execution Context Guide](guide/context.md)** - RoutingContext, parent chain, ContextVar
- **[Plugin Guide](guide/plugins.md)** - Learn to create custom plugins
- **[Hierarchies Guide](guide/hierarchies.md)** - Master nested routers
- **[Best Practices](guide/best-practices.md)** - Production-ready patterns
- **[API Reference](api/reference.md)** - Complete API documentation

## Need Help?

- **Examples**: Check the [examples](https://github.com/genropy/genro-routes/tree/main/examples) directory
- **Issues**: Report bugs on [GitHub Issues](https://github.com/genropy/genro-routes/issues)
