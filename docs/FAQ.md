# Genro Routes - Frequently Asked Questions

<!-- test: test_router_basic.py::test_orders_quick_example -->

## What is Genro Routes?

### What problem does Genro Routes solve?

**Question**: I have many methods in a class and want to call them dynamically by string name. How can I organize them better?

**Answer**: Genro Routes lets you create a "router" that maps string names to Python methods, with per-instance isolation and hierarchy support. Instead of manually managing a dictionary of handlers, you use the `@route()` decorator and Genro Routes handles the rest.

<!-- test: test_router_basic.py::test_orders_quick_example -->

**Example**:
```python
from genro_routes import RoutingClass, route

class OrdersAPI(RoutingClass):
    @route()
    def list(self):
        return ["order-1", "order-2"]

    @route()
    def create(self, payload: dict):
        return {"status": "created", **payload}

orders = OrdersAPI()
orders.route.node("list")()  # Calls list()
orders.route.node("create")({"name": "order-3"})  # Calls create()
```

### Genro Routes vs function dictionary?

**Question**: Why not just use a dictionary `{"list": self.list, "create": self.create}`?

**Answer**: Genro Routes offers:

- **Plugin system**: add logging, validation, audit without touching handlers
- **Hierarchies**: organize routers in trees with `attach_instance()` (method on `RoutingClass`)
- **Metadata**: each handler can have tags, channels, configurations
- **Introspection**: `router.nodes()` to explore structure
- **Isolation**: each instance has its own router with independent plugins

For simple apps, a dictionary may suffice. For complex services, Genro Routes provides structure and extensibility.

### Is Genro Routes a web framework?

**Question**: Does Genro Routes replace FastAPI/Flask?

**Answer**: **No**. Genro Routes is an **internal** routing engine for organizing Python methods. It doesn't handle HTTP, WebSocket, or networking. It's used **inside** an application for:
- CLI tools
- Internal orchestrators
- Service composition
- Dynamic dashboards

You can use Genro Routes **alongside** FastAPI to organize your internal handlers before exposing them via HTTP.

## Core Concepts

### What is a Router?

**Question**: What exactly does a `Router` do?

**Answer**: A `Router` is an object that:

1. **Registers handlers**: methods decorated with `@route()`
2. **Resolves by name**: `router.node("method_name")` → callable RouterNode
3. **Applies plugins**: intercepts decoration and execution
4. **Is isolated per instance**: every `RoutingClass` instance owns exactly one router, auto-created and exposed as the `route` property

```python
class Service(RoutingClass):
    def __init__(self, label: str):
        self.label = label

    @route()
    def info(self):
        return f"service:{self.label}"

s1 = Service("alpha")
s2 = Service("beta")
s1.route.node("info")()  # "service:alpha"
s2.route.node("info")()  # "service:beta"
```

Each instance (`s1`, `s2`) has a **separate and isolated** router. You never call `Router(...)` yourself.

### How does the @route decorator work?

**Question**: What does `@route()` exactly do?

<!-- test: test_router_basic.py::test_prefix_and_name_override -->

**Answer**: The `@route()` decorator marks a method for registration on the class's single router. The router is created lazily on first access of `self.route` and automatically discovers all marked methods. All options are keyword-only.

**Options**:
```python
@route()  # Auto name (method name)
def list_users(self): ...

@route(name="users")  # Explicit name
def handle_users(self): ...

# With self.route.prefix = "handle_" set in __init__
@route()
def handle_create(self): ...  # Registered as "create" (strips prefix)
```

### What is RoutingClass?

**Question**: Do I always need to inherit from `RoutingClass`?

**Answer**: **Yes**. `RoutingClass` is the mixin that binds a class to its router:

- `obj.route` — the instance's single router, created lazily (read-only property)
- `obj.routing` — proxy for configuration and lookup (`configure()`, `get_router()`, `instance()`)
- `obj.attach_instance(child, name=...)` — connects child instances into a hierarchy
- `obj.ctx` — execution context with parent-chain lookup

A `Router` can only be owned by a `RoutingClass` instance.

## Hierarchies and Child Routers

### How do I organize nested routers?

**Question**: I have an application with modules (sales, finance, admin) that I want to organize hierarchically. How?

**Answer**: Use `attach_instance()` (a method on `RoutingClass`) to connect child instances:

```python
class Dashboard(RoutingClass):
    def __init__(self):
        self.sales = SalesModule()
        self.finance = FinanceModule()

        # Attach child instances — each child's router is linked under the alias
        self.attach_instance(self.sales, name="sales")
        self.attach_instance(self.finance, name="finance")

dashboard = Dashboard()
# Access with path separator
dashboard.route.node("sales/report")()
dashboard.route.node("finance/summary")()
```

For a pure grouping level without a dedicated class, attach a `Section`:

```python
from genro_routes import Section

dashboard.attach_instance(Section("Admin area"), name="admin")
```

### How do I access child routers?

**Question**: Once connected, how do I call child handlers?

**Answer**: Use **path separator** `/`:
```python
# Path separator
dashboard.route.node("sales/report")()

# Or direct access
dashboard.sales.route.node("report")()

# Introspection
nodes = dashboard.route.nodes()
# {
#   "entries": {...},
#   "routers": {
#     "sales": {...},
#     "finance": {...}
#   }
# }
```

### Do plugins inherit to children?

**Question**: If I attach a plugin to the parent router, do children see it?

**Answer**: **Yes, automatically**. Plugins propagate from parent to children:

```python
class Parent(RoutingClass):
    def __init__(self):
        self.route.plug("logging")
        self.child_obj = Child()
        self.attach_instance(self.child_obj, name="child")

# Child automatically inherits logging plugin
parent = Parent()
parent.route.node("child/method")()  # Logged via inherited plugin
```

## Plugin System

### What are plugins?

**Question**: What is a plugin in Genro Routes and what is it for?

**Answer**: A **plugin** extends router behavior without modifying handlers. Plugins intercept:

1. **Decoration** (`on_decore`): when a handler is registered
2. **Execution** (`wrap_handler`): when a handler is called

**Use cases**:

- **Logging**: record all calls
- **Validation**: check input with Pydantic
- **Audit**: track who/when/what

### How do I use built-in plugins?

**Question**: Does Genro Routes have ready-to-use plugins?

<!-- test: test_plugins_new.py::test_logging_plugin_runs_per_instance -->

**Answer**: Yes, 5 built-in plugins:

**1. LoggingPlugin** - Automatic logging
```python
self.route.plug("logging")     # in __init__
svc.route.node("method")()     # Auto-logs the call
```

**2. PydanticPlugin** - Input validation + response schemas
<!-- test: test_pydantic_plugin.py::test_pydantic_plugin_accepts_valid_input -->

```python
self.route.plug("pydantic")    # in __init__

@route()
def concat(self, text: str, number: int = 1) -> str:
    return f"{text}:{number}"

svc.route.node("concat")("hello", 3)    # OK → "hello:3"
svc.route.node("concat")(123, "oops")   # ValidationError

# Response schema auto-generated from return type annotation
svc.route._entries["concat"].metadata["pydantic"]["response_schema"]
# {"type": "string"}
```

**3. AuthPlugin** - Role-based access control
```python
self.route.plug("auth")        # in __init__

@route(auth_rule="admin")
def admin_action(self):
    return "secret"

svc.route.node("admin_action", auth_tags="admin")()  # OK
svc.route.node("admin_action", auth_tags="guest")()  # NotAuthorized
```

**4. EnvPlugin** - Capability-based filtering

```python
self.route.plug("env")         # in __init__

@route(env_requires="redis")
def cached_action(self):
    return "cached"

# Entry only visible if instance has "redis" capability
```

**5. OpenAPIPlugin** - Schema metadata and response schemas

```python
self.route.plug("openapi")     # in __init__

@route(openapi_method="post", openapi_tags="users")
def create_user(self, name: str) -> dict:
    return {"name": name}

# Provides metadata for OpenAPI schema generation
# Response schemas auto-included from return type annotations
```

### How do I configure plugins at runtime?

**Question**: I want to change plugin configuration after creating the router.

<!-- test: test_router_edge_cases.py::test_routed_configure_updates_plugins_global_and_local -->

**Answer**: Use `routing.configure()`:

```python
# Global for all handlers
obj.routing.configure("logging/_all_", before=False)

# For specific handler
obj.routing.configure("logging/create", enabled=False)

# With glob patterns
obj.routing.configure("logging/admin_*", enabled=False)

# Query configuration — returns the router description dict
# (keys: name, plugins, entries, routers)
report = obj.routing.configure("?")
```

### Can I create custom plugins?

**Question**: How do I write a custom plugin?

**Answer**: Inherit from `BasePlugin` and implement the hooks:

```python
from genro_routes.plugins import BasePlugin

class AuditPlugin(BasePlugin):
    def on_decore(self, router, func, entry):
        """Called when handler is registered"""
        entry.metadata["audited"] = True

    def wrap_handler(self, router, entry, call_next):
        """Called when handler is executed"""
        def wrapper(*args, **kwargs):
            print(f"[AUDIT] Calling {entry.name}")
            result = call_next(*args, **kwargs)
            print(f"[AUDIT] Result: {result}")
            return result
        return wrapper

# Register globally, then attach in __init__
Router.register_plugin(AuditPlugin)
self.route.plug("audit")
```

## Advanced Use Cases

### How do I handle errors and defaults?

**Question**: What happens if I call a non-existent handler?

**Answer**: Check `node.error` to see if the node resolved correctly:

```python
# node() returns a RouterNode - check error status
node = router.node("missing")
if node.error:
    print(f"Handler error: {node.error}")

# RouterNode is always callable - errors raise on invocation
node = router.node("my_handler")
result = node()  # Invoke the handler (raises if error)

# Calling a node with error raises the appropriate exception
from genro_routes import NotFound
try:
    router.node("missing")()
except NotFound:
    print("Handler not found")
```

### What exceptions can node() raise?

**Question**: What exceptions should I catch when calling a RouterNode?

**Answer**: Three main exceptions:

- `NotFound`: Path not found, no default_entry, or partial args don't match signature
- `NotAuthorized`: Auth tags provided but don't match (403)
- `NotAuthenticated`: Auth required but not provided (401)

```python
from genro_routes import NotFound, NotAuthorized, NotAuthenticated

try:
    router.node("handler")()
except NotAuthenticated:
    # 401 - no auth provided
    pass
except NotAuthorized:
    # 403 - auth provided but wrong
    pass
except NotFound:
    # 404 - path not found
    pass
```

You can also map these to custom exceptions:

```python
node = router.node("handler", errors={
    'not_found': HTTPNotFound,
    'not_authorized': HTTPForbidden,
    'not_authenticated': HTTPUnauthorized,
})
```

### What is a root node?

**Question**: What do I get when calling `node("/")`?

**Answer**: A **root node** pointing to the router's default entry:

```python
node = router.node("/")  # or node("")

# Check node state
node.path     # ""
node.error    # None if default_entry exists

# If default_entry exists
node()            # calls default_entry

# If no default_entry
node()            # raises NotFound
```

### How do I introspect the structure?

**Question**: I want to see all registered entries and child routers.

**Answer**: Use `nodes()`:

```python
# Structure snapshot
nodes = router.nodes()
# {
#   "name": "route",
#   "router": <Router>,
#   "instance": <owner>,
#   "plugin_info": {...},
#   "entries": {
#     "list": {"callable": <function>, "doc": "...", ...},
#     "create": {...}
#   },
#   "routers": {
#     "sales": {...}
#   }
# }

# With filters (using AuthPlugin)
admin_only = router.nodes(auth_tags="admin")

# Generate OpenAPI schema
schema = router.nodes(mode="openapi")
```

**`nodes()` parameters**:

- `basepath`: Start from a specific point in the hierarchy
- `lazy`: Return router references instead of expanding
- `mode`: Output format (`"openapi"` for OpenAPI schema)

## Comparisons

### Genro Routes vs decorator dispatch?

**Question**: Why not use `functools.singledispatch`?

**Answer**:

- `singledispatch` → dispatch by **type** of first argument
- Genro Routes → dispatch by **string name** with metadata, plugins, hierarchies

Different use cases: `singledispatch` for typed polymorphism, Genro Routes for dynamic routing.

## Troubleshooting

### "No plugin named 'X' attached to router"

**Problem**: `AttributeError: No plugin named 'logging' attached to router`

**Solution**: The plugin wasn't attached. Use `.plug()`:
```python
self.route.plug("logging")  # Now self.route.logging exists
```

### "Handler name collision"

**Problem**: Two methods with the same name registered on the same router.

**Solution**: Use explicit names or prefixes:
```python
@route(name="create_user")
def handle_create_user(self): ...

@route(name="create_order")
def handle_create_order(self): ...
```

### Plugins don't propagate to children

**Problem**: Children don't see parent plugins.

**Solution**: Make sure to attach plugins to the parent router **before** connecting children:
```python
# CORRECT
self.route.plug("logging")
self.attach_instance(child, name="child")  # Child inherits logging

# WRONG
self.attach_instance(child, name="child")
self.route.plug("logging")  # Child does NOT inherit
```

### ValidationError with Pydantic

**Problem**: `ValidationError` even with correct input.

**Solution**: Verify:

1. PydanticPlugin attached: `self.route.plug("pydantic")`
2. Type hint correct: `def method(self, req: MyModel)`
3. Input is dict or model instance: `svc.route.node("method")({"field": "value"})`

## Best Practices

### When should I use Genro Routes?

✅ **Use Genro Routes when**:

- You have many handlers to organize dynamically
- You want to extend behavior with plugins
- You need hierarchical routing (parent/child)
- You need to expose handlers via multiple interfaces (CLI/HTTP/WS)

❌ **Don't use Genro Routes when**:
- You only have 2-3 simple methods (overkill)
- You don't need dynamic dispatch
- You prefer explicit/static routing

### Does plugin order matter?

**Question**: Is the order of `.plug()` important?

**Answer**: **Yes**. Plugins are applied **in attachment order**:
```python
self.route.plug("logging").plug("pydantic")
# Execution: logging → pydantic → handler → pydantic → logging
```

Outer logging sees everything, inner Pydantic validates.

### How do I test code with Genro Routes?

**Question**: How do I write tests for handlers with Genro Routes?

**Answer**: Test directly or via router:
```python
# Direct test
def test_handler_logic():
    obj = MyClass()
    assert obj.my_handler({"input": "test"}) == expected

# Test via router
def test_router_integration():
    obj = MyClass()
    node = obj.route.node("my_handler")
    assert node({"input": "test"}) == expected
```

## Context and Shared State

### How do I access a database connection from my handlers?

**Question**: My handlers need access to a database connection, the current user, or session data. How do I provide this without coupling to a specific adapter?

**Answer**: Use `RoutingContext`. The adapter creates a context, attaches what it needs, and sets it on any `RoutingClass` instance. All handlers read it via `self.ctx`:

```python
from genro_routes import RoutingClass, RoutingContext, route

class OrderService(RoutingClass):
    @route()
    def list_orders(self):
        return self.ctx.db.query("SELECT * FROM orders")

# Adapter sets up context
ctx = RoutingContext()
ctx.db = db_connection
ctx.user = current_user

svc = OrderService()
svc.ctx = ctx  # stored in _ctx slot — children inherit via parent chain
```

For layered contexts (server → app → request), use `RoutingContext(parent=parent_ctx)` — missing attributes walk up the parent chain automatically.

See the **[Execution Context Guide](guide/context.md)** for the full reference.

### What happened to DbRoutingClass?

**Question**: I was using `DbRoutingClass` to propagate `db` through the hierarchy. Where did it go?

**Answer**: `DbRoutingClass` has been removed. Database connections now live in the execution context:

```python
# Old (removed)
class MyServer(DbRoutingClass):
    def __init__(self, db):
        self.db = db  # propagated via _routing_parent

# New
ctx = RoutingContext()
ctx.db = db_connection
svc.ctx = ctx
# Handlers: self.ctx.db
```

The parent chain in `RoutingContext` provides the same propagation behavior — set `db` once at the top level, and all handlers read it via `self.ctx.db`.

## Useful Links

- **[Quick Start](quickstart.md)** - Get started in 5 minutes
- **[Basic Usage](guide/basic-usage.md)** - Fundamental concepts
- **[Execution Context](guide/context.md)** - RoutingContext, parent chain, slot-based ctx
- **[Plugin Guide](guide/plugins.md)** - Plugin development
- **[Hierarchies](guide/hierarchies.md)** - Nested routing
- **[API Reference](api/reference.md)** - Complete documentation

## Contributing

Have more questions? [Open an issue](https://github.com/genropy/genro-routes/issues) or contribute to this FAQ!
