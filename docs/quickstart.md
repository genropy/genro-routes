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
from genro_routes import RoutingClass, route

class Service(RoutingClass):
    def __init__(self, label: str):
        self.label = label

    @route()
    def describe(self):
        return f"service:{self.label}"

# Each instance is isolated
first = Service("alpha")
second = Service("beta")

assert first.route.node("describe")() == "service:alpha"
assert second.route.node("describe")() == "service:beta"
```

**Key concept**: Every `RoutingClass` owns exactly one router, created automatically and exposed as the `route` property - each instance gets its own isolated router. You never instantiate `Router` yourself.

## Custom Entry Names

<!-- test: test_router_basic.py::test_prefix_and_name_override -->

[From test](https://github.com/genropy/genro-routes/blob/main/tests/test_router_basic.py#L150-L154)

Use prefixes and explicit names for cleaner method registration:

```python
class SubService(RoutingClass):
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.route.prefix = "handle_"

    @route()
    def handle_list(self):
        return f"{self.prefix}:list"

    @route(name="detail")
    def handle_detail(self, ident: int):
        return f"{self.prefix}:detail:{ident}"

sub = SubService("users")

# Prefix stripped: "handle_list" → "list"
assert sub.route.node("list")() == "users:list"

# Custom name used: "handle_detail" → "detail"
assert sub.route.node("detail")(10) == "users:detail:10"
```

Router options like `prefix` and `description` are set on the existing router in `__init__` (binding is lazy, so this is race-free).

## One Class, One Router

<!-- test: test_router_basic.py::TestSingleRouterDefault::test_route_without_args_uses_single_router -->

`@route()` always registers the method on the class's single router. A class with no plugins or router options needs no `__init__` at all:

```python
class Table(RoutingClass):
    @route()
    def add(self, data):
        return f"added:{data}"

t = Table()
assert t.route.node("add")("x") == "added:x"
```

Need more than one routing surface (e.g. `api` and `admin`)? Compose separate `RoutingClass` instances with `attach_instance()` - see [Building Hierarchies](#building-hierarchies) below.

## Building Hierarchies

Create nested router structures:

```python
class RootAPI(RoutingClass):
    def __init__(self):
        self.users = SubService("users")
        self.products = SubService("products")

        self.attach_instance(self.users, name="users")
        self.attach_instance(self.products, name="products")

root = RootAPI()

# Access with path separator
assert root.route.node("users/list")() == "users:list"
assert root.route.node("products/detail")(5) == "products:detail:5"
```

## Adding Plugins

<!-- test: test_router_basic.py::test_plugins_are_per_instance_and_accessible -->

[From test](https://github.com/genropy/genro-routes/blob/main/tests/test_router_basic.py#L157-L165)

Extend behavior with plugins. Built-in plugins (`logging`, `pydantic`, `auth`, `env`, `channel`) are pre-registered.

```python
class PluginService(RoutingClass):
    def __init__(self):
        self.route.plug("logging")

    @route()
    def do_work(self):
        return "ok"

svc = PluginService()
result = svc.route.node("do_work")()  # Automatically logged
```

## Validating Arguments

<!-- test: test_pydantic_plugin.py::test_pydantic_plugin_accepts_valid_input -->

[From test](https://github.com/genropy/genro-routes/blob/main/tests/test_pydantic_plugin.py#L36-L41)

Use Pydantic for automatic validation:

```python
class ValidateService(RoutingClass):
    def __init__(self):
        self.route.plug("pydantic")

    @route()
    def concat(self, text: str, number: int = 1) -> str:
        return f"{text}:{number}"

svc = ValidateService()

# Valid inputs
assert svc.route.node("concat")("hello", 3) == "hello:3"
assert svc.route.node("concat")("hi") == "hi:1"

# Invalid inputs raise ValidationError
# svc.route.node("concat")(123, "oops")  # ValidationError!
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
        self.route.plug("pydantic")

    @route()
    def health(self) -> StatusResponse:
        return {"ok": True, "message": "running"}

svc = HealthService()

# Response schema is generated automatically
entry = svc.route._entries["health"]
schema = entry.metadata["pydantic"]["response_schema"]
# {"type": "object", "properties": {"ok": {"type": "boolean"}, "message": {"type": "string"}}, ...}
```

Supported types: `TypedDict`, `dict[str, T]`, `list[T]`, `str`, `int`, `bool`, and any type Pydantic can serialize. TypedDict requires Python 3.12+.

## Execution Context

Handlers need access to shared state (database, user, session) without
knowing which adapter provides it. Use `RoutingContext`:

```python
from genro_routes import RoutingClass, RoutingContext, route

class OrderService(RoutingClass):
    @route()
    def list_orders(self):
        return self.ctx.db.query("SELECT * FROM orders")

# Create a context and set it
ctx = RoutingContext()
ctx.db = my_database

svc = OrderService()
svc.ctx = ctx
svc.route.node("list_orders")()  # handler reads self.ctx.db
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
