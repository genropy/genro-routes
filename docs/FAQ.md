# Genro Routes - Frequently Asked Questions

<!-- test: test_router_basic.py::test_orders_quick_example -->

## What is Genro Routes?

### What problem does Genro Routes solve?

**Question**: I have many methods in a class and want to call them dynamically by string name. How can I organize them better?

**Answer**: Genro Routes lets you create a "router" that maps string names to Python methods, with per-instance isolation and hierarchy support. Instead of manually managing a dictionary of handlers, you use the `@route()` decorator and Genro Routes handles the rest.

<!-- test: test_router_basic.py::test_orders_quick_example -->

**Example**:
```python
from genro_routes import RoutingClass, Router, route

class OrdersAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="orders")

    @route("orders")
    def list(self):
        return ["order-1", "order-2"]

    @route("orders")
    def create(self, payload: dict):
        return {"status": "created", **payload}

orders = OrdersAPI()
orders.api.node("list")()  # Calls list()
orders.api.node("create")({"name": "order-3"})  # Calls create()
```

### Genro Routes vs function dictionary?

**Question**: Why not just use a dictionary `{"list": self.list, "create": self.create}`?

**Answer**: Genro Routes offers:

- **Plugin system**: add logging, validation, audit without touching handlers
- **Hierarchies**: organize routers in trees with `attach_instance()`
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
4. **Is isolated per instance**: each object has its own router

```python
class Service(RoutingClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="api")

    @route("api")
    def info(self):
        return f"service:{self.label}"

s1 = Service("alpha")
s2 = Service("beta")
s1.api.node("info")()  # "service:alpha"
s2.api.node("info")()  # "service:beta"
```

Each instance (`s1`, `s2`) has a **separate and isolated** router.

### How does the @route decorator work?

**Question**: What does `@route("api")` exactly do?

<!-- test: test_router_basic.py::test_prefix_and_name_override -->

**Answer**: The `@route("router_name")` decorator marks a method to be registered in a specific router. When you create the instance and call `Router(self, name="api")`, the router finds all methods marked with `@route("api")` and registers them automatically.

**Options**:
```python
@route("api")  # Auto name (method name)
def list_users(self): ...

@route("api", name="users")  # Explicit name
def handle_users(self): ...

# With Router(prefix="handle_")
@route("api")
def handle_create(self): ...  # Registered as "create" (strips prefix)
```

### What is RoutingClass?

**Question**: Do I always need to inherit from `RoutingClass`?

**Answer**: **Recommended but not required**. `RoutingClass` provides:

- `obj.routing` proxy to access all routers
- `obj.routing.configure()` for global configuration
- Automatic router registry management

**Without RoutingClass** you can still use `Router` directly, but you lose the unified proxy.

## Hierarchies and Child Routers

### How do I organize nested routers?

**Question**: I have an application with modules (sales, finance, admin) that I want to organize hierarchically. How?

**Answer**: Use `attach_instance()` to connect child instances:

```python
class Dashboard(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.sales = SalesModule()
        self.finance = FinanceModule()

        # Attach child instances
        self.api.attach_instance(self.sales, name="sales")
        self.api.attach_instance(self.finance, name="finance")

dashboard = Dashboard()
# Access with path separator
dashboard.api.node("sales/report")()
dashboard.api.node("finance/summary")()
```

### How do I access child routers?

**Question**: Once connected, how do I call child handlers?

**Answer**: Use **path separator** `/`:
```python
# Path separator
dashboard.api.node("sales/report")()

# Or direct access
dashboard.sales.api.node("report")()

# Introspection
nodes = dashboard.api.nodes()
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
        self.api = Router(self, name="api").plug("logging", level="debug")
        self.child_obj = Child()
        self.api.attach_instance(self.child_obj, name="child")

# Child automatically inherits logging plugin
parent = Parent()
parent.api.node("child/method")()  # Logs with level=debug
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
router = Router(self, name="api").plug("logging")
router.node("method")()  # Auto-logs the call
```

**2. PydanticPlugin** - Input validation
<!-- test: test_pydantic_plugin.py::test_pydantic_plugin_accepts_valid_input -->

```python
from pydantic import BaseModel

class CreateRequest(BaseModel):
    name: str
    count: int

@route("api")
def create(self, req: CreateRequest):
    return {"status": "created"}

router.plug("pydantic")
router.node("create")({"name": "test", "count": 5})  # OK
router.node("create")({"name": "test"})  # ValidationError
```

**3. AuthPlugin** - Role-based access control
```python
@route("api", auth_rule="admin")
def admin_action(self):
    return "secret"

router.plug("auth")
router.node("admin_action", auth_tags="admin")()  # OK
router.node("admin_action", auth_tags="guest")()  # NotAuthorized
```

**4. EnvPlugin** - Capability-based filtering

```python
@route("api", env_requires="redis")
def cached_action(self):
    return "cached"

router.plug("env")
# Entry only visible if instance has "redis" capability
```

**5. OpenAPIPlugin** - Schema metadata

```python
@route("api", openapi_method="post", openapi_tags="users")
def create_user(self, name: str) -> dict:
    return {"name": name}

router.plug("openapi")
# Provides metadata for OpenAPI schema generation
```

### How do I configure plugins at runtime?

**Question**: I want to change plugin configuration after creating the router.

<!-- test: test_router_edge_cases.py::test_routed_configure_updates_plugins_global_and_local -->

**Answer**: Use `routing.configure()`:

```python
# Global for all handlers
obj.routing.configure("api:logging", level="warning")

# For specific handler
obj.routing.configure("api:logging/create", enabled=False)

# With wildcards
obj.routing.configure("*:logging/*", level="debug")

# Query configuration
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

# Register and use
Router.register_plugin(AuditPlugin)
router = Router(self, name="api").plug("audit")
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
#   "name": "api",
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
router.plug("logging")  # Now router.logging exists
```

### "Handler name collision"

**Problem**: Two methods with the same name registered on the same router.

**Solution**: Use explicit names or prefixes:
```python
@route("api", name="create_user")
def handle_create_user(self): ...

@route("api", name="create_order")
def handle_create_order(self): ...
```

### Plugins don't propagate to children

**Problem**: Children don't see parent plugins.

**Solution**: Make sure to connect children **after** attaching plugins:
```python
# CORRECT
router.plug("logging")
router.attach_instance(child, name="child")  # Child inherits logging

# WRONG
router.attach_instance(child, name="child")
router.plug("logging")  # Child does NOT inherit
```

### ValidationError with Pydantic

**Problem**: `ValidationError` even with correct input.

**Solution**: Verify:

1. PydanticPlugin attached: `router.plug("pydantic")`
2. Type hint correct: `def method(self, req: MyModel)`
3. Input is dict or model instance: `router.node("method")({"field": "value"})`

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
router.plug("logging").plug("pydantic")
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
    node = obj.api.node("my_handler")
    assert node({"input": "test"}) == expected
```

## Useful Links

- **[Quick Start](quickstart.md)** - Get started in 5 minutes
- **[Basic Usage](guide/basic-usage.md)** - Fundamental concepts
- **[Plugin Guide](guide/plugins.md)** - Plugin development
- **[Hierarchies](guide/hierarchies.md)** - Nested routing
- **[API Reference](api/reference.md)** - Complete documentation

## Contributing

Have more questions? [Open an issue](https://github.com/genropy/genro-routes/issues) or contribute to this FAQ!
