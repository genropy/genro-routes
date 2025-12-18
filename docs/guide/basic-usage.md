# Basic Usage

This guide covers Genro Routes' core features with practical examples derived from the test suite.

## Overview

Genro Routes provides instance-scoped routing with hierarchical organization and plugin support. Each router instance is independent with its own plugin state.

**Key concepts**:

- Routers are instantiated at runtime: `Router(self, name="api")`
- Methods are marked with `@route("router_name")` decorator
- Each instance gets isolated routing state
- Plugins apply per-instance, not globally

## Creating Your First Router

<!-- test: test_router_basic.py::test_instance_bound_methods_are_isolated -->

Create a service with instance-scoped routing:

```python
from genro_routes import RoutedClass, Router, route

class Service(RoutedClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="api")

    @route("api")
    def describe(self):
        return f"service:{self.label}"

# Each instance is isolated
first = Service("alpha")
second = Service("beta")

assert first.api.get("describe")() == "service:alpha"
assert second.api.get("describe")() == "service:beta"
```

**Key points**:

- `Router(self, name="api")` creates instance-scoped router in `__init__`
- `@route("api")` marks method for registration
- `RoutedClass` is **required** - all classes using `Router` must inherit from it
- Each instance has independent routing state

## Registering Handlers

<!-- test: test_router_edge_cases.py::test_router_auto_registers_marked_methods_and_validates_plugins -->

Methods are automatically registered when decorated with `@route`:

```python
class API(RoutedClass):
    def __init__(self):
        self.routes = Router(self, name="routes")

    @route("routes")
    def echo(self, value: str):
        return value

    @route("routes", name="alt_name")
    def action(self):
        return "executed"

api = API()

# Direct name resolution
assert api.routes.get("echo")("hello") == "hello"

# Custom name resolution
assert api.routes.get("alt_name")() == "executed"
```

**Registration happens automatically** when you inherit from `RoutedClass` and instantiate routers in `__init__`.

## Default Router with `main_router`

<!-- test: test_router_basic.py::TestMainRouterAttribute::test_route_without_args_uses_main_router -->

When a class uses a single router consistently, you can define `main_router` as a class attribute to avoid repeating the router name:

```python
class Table(RoutedClass):
    main_router = "table"  # Default router for @route()

    def __init__(self):
        self.table = Router(self, name="table")

    @route()  # Uses main_router automatically
    def add(self, data):
        return f"added:{data}"

    @route()  # Also uses main_router
    def remove(self, id):
        return f"removed:{id}"

    @route("other")  # Explicit name overrides main_router
    def special(self):
        return "special"

t = Table()
assert t.table.get("add")("x") == "added:x"
assert t.table.get("remove")(1) == "removed:1"
```

**Benefits**:

- Less repetition when all methods target the same router
- Explicit `@route("name")` still works to override
- Inheritance works: subclasses can override `main_router`

### Accessing the Default Router

You can also access the default router programmatically via the `default_router` property:

```python
class SingleAPI(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def ping(self):
        return "pong"

svc = SingleAPI()

# When there's only one router, it becomes the default
assert svc.default_router is svc.api

# With main_router defined, it takes priority
class MultiAPI(RoutedClass):
    main_router = "admin"

    def __init__(self):
        self.api = Router(self, name="api")
        self.admin = Router(self, name="admin")

m = MultiAPI()
assert m.default_router is m.admin  # main_router takes priority
```

## Calling Handlers

<!-- test: test_router_runtime_extras.py::test_router_call_and_nodes_structure -->

Use `get()` to retrieve handlers and `call()` for direct invocation:

```python
class Calculator(RoutedClass):
    def __init__(self):
        self.ops = Router(self, name="ops")

    @route("ops")
    def add(self, a: int, b: int):
        return a + b

calc = Calculator()

# Via get() - returns callable
handler = calc.ops.get("add")
assert handler(2, 3) == 5

# Via call() - invokes directly
result = calc.ops.call("add", 10, 20)
assert result == 30
```

**Difference**:

- `get(name)` returns the callable (for reuse)
- `call(name, *args, **kwargs)` invokes immediately

## Using Prefixes and Custom Names

<!-- test: test_router_basic.py::test_prefix_and_name_override -->

Clean up method names with prefixes and provide alternative names with the `name` option:

```python
class SubService(RoutedClass):
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
assert sub.routes.get("list")() == "users:list"

# Custom name used: "handle_detail" → "detail"
assert sub.routes.get("detail")(10) == "users:detail:10"
```

**Benefits**:

- Prefixes keep method names organized in code
- Explicit names provide cleaner external APIs
- Router resolves both automatically

## Default Handlers

<!-- test: test_router_basic.py::test_get_with_default_returns_callable -->

Provide fallback handlers when routes don't exist:

```python
class Fallback(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def known_action(self):
        return "success"

fb = Fallback()

# Existing handler
assert fb.api.get("known_action")() == "success"

# Non-existing with default
default_fn = lambda: "fallback"
assert fb.api.get("missing", default_handler=default_fn)() == "fallback"

# Without default returns None
assert fb.api.get("missing") is None
```

**Use defaults to**:

- Handle optional functionality gracefully
- Provide "not found" handlers
- Implement fallback behavior

**Note**: `get()` can also return a child router if the path points to one (see [Hierarchies](hierarchies.md)).

## Exceptions: NotFound and NotAuthorized

<!-- test: test_filter_plugin.py::TestGetAndCallWithFilters -->

Genro Routes provides two exceptions for handling routing errors:

```python
from genro_routes import NotFound, NotAuthorized, UNAUTHORIZED

# NotFound - raised when entry doesn't exist
# NotAuthorized - raised when entry exists but access is denied by filters
```

**When using filters with `get()` and `call()`**:

```python
from genro_routes import RoutedClass, Router, route, NotFound, NotAuthorized

class SecureAPI(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("filter")

    @route("api", filter_tags="admin")
    def admin_action(self):
        return "admin only"

    @route("api", filter_tags="public")
    def public_action(self):
        return "public"

api = SecureAPI()

# Entry exists and tag matches - returns handler
handler = api.api.get("admin_action", filter_tags="admin")
assert handler() == "admin only"

# Entry exists but tag doesn't match - raises NotAuthorized
try:
    api.api.get("admin_action", filter_tags="public")
except NotAuthorized as e:
    print(f"Access denied: {e.selector}")  # "admin_action"

# Entry doesn't exist - get() returns None, call() raises NotFound
result = api.api.get("nonexistent")  # None
try:
    api.api.call("nonexistent")
except NotFound as e:
    print(f"Not found: {e.selector}")  # "nonexistent"
```

**Exception attributes**:

- `selector`: The path that was requested
- `router_name`: The router where the error occurred

**Using `node()` with filters**:

The `node()` method also supports filters and returns `callable: UNAUTHORIZED` when access is denied:

```python
from genro_routes import UNAUTHORIZED

info = api.api.node("admin_action", filter_tags="public")
if info.get("callable") == UNAUTHORIZED:
    print("Access denied")
else:
    handler = info["callable"]
    result = handler()
```

## Catch-All Routing with `default_entry`

<!-- test: test_router_basic.py::TestDefaultEntryWithPartial -->

Routers have a `default_entry` parameter (default: `"index"`) that enables catch-all routing patterns when combined with `partial=True`:

```python
class FileServer(RoutedClass):
    def __init__(self):
        # default_entry="index" is the default, but can be customized
        self.api = Router(self, name="api", default_entry="serve")

    @route("api")
    def serve(self, *path_segments):
        return f"Serving: {'/'.join(path_segments)}"

server = FileServer()

# When partial=True and path can't be fully resolved,
# unconsumed segments become arguments to the default_entry handler
result = server.api.get("docs/api/reference", partial=True)
# Returns: functools.partial(server.serve, "docs", "api", "reference")
assert result() == "Serving: docs/api/reference"
```

**Key behaviors**:

- `default_entry` specifies which handler to use for unresolved paths (default: `"index"`)
- `partial=True` enables this behavior, returning a `functools.partial`
- Unconsumed path segments are passed as positional arguments
- If `default_entry` handler doesn't exist, raises `ValueError`

**Use cases**:

- File servers with arbitrary path depth
- Catch-all handlers for dynamic routing
- Pass-through routes to external services

## Building Hierarchies

<!-- test: test_router_basic.py::test_dotted_path_and_nodes_with_attached_child -->

Create nested router structures with dotted path access:

```python
class SubService(RoutedClass):
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.routes = Router(self, name="routes", prefix="handle_")

    @route("routes")
    def handle_list(self):
        return f"{self.prefix}:list"

    @route("routes", name="detail")
    def handle_detail(self, ident: int):
        return f"{self.prefix}:detail:{ident}"

class RootAPI(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.users = SubService("users")
        self.products = SubService("products")

        self.api.attach_instance(self.users, name="users")
        self.api.attach_instance(self.products, name="products")

root = RootAPI()

# Access with path separator
assert root.api.get("users/list")() == "users:list"
assert root.api.get("products/detail")(5) == "products:detail:5"
```

**Hierarchies enable**:

- Organized service composition
- Logical grouping of related handlers
- Namespace isolation

## Introspection

<!-- test: test_router_basic.py::test_dotted_path_and_nodes_with_attached_child -->

Inspect router structure and registered handlers:

```python
class Inspectable(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.child_service = SubService("child")
        self.api.attach_instance(self.child_service, name="sub")

    @route("api")
    def action(self):
        pass

insp = Inspectable()

# Get metadata (single source: nodes)
info = insp.api.nodes()
assert "action" in info["entries"]
assert "sub" in info["routers"]

# Get nodes starting from a specific path
sub_info = insp.api.nodes(basepath="sub")
assert "list" in sub_info["entries"]

# Use lazy=True for on-demand expansion of children
lazy_info = insp.api.nodes(lazy=True)
assert callable(lazy_info["routers"]["sub"])  # Callable, not expanded
sub_expanded = lazy_info["routers"]["sub"]()  # Expand on demand
```

**`nodes()` parameters**:

- `basepath`: Start from a specific point in the hierarchy
- `lazy`: Return callables for child routers instead of expanding recursively
- `mode`: Output format mode (e.g., `"openapi"` for OpenAPI schema generation)

**Output modes**:

- `None` (default): Standard introspection format with entries, routers, plugin_info
- `"openapi"`: Generate OpenAPI 3.0 schema with paths and operations

```python
# Generate OpenAPI schema
schema = insp.api.nodes(mode="openapi")
# Or use the shortcut method
schema = insp.api.openapi()
```

**Use `nodes()` to**:

- Generate API documentation (with `mode="openapi"`)
- Debug routing issues
- Validate configuration
- Build dynamic UIs that expand on demand (with `lazy=True`)

## Next Steps

Now that you understand the basics:

- **[Plugin Guide](plugins.md)** - Extend functionality with plugins
- **[Hierarchies Guide](hierarchies.md)** - Advanced nested routing patterns
- **[Best Practices](best-practices.md)** - Production-ready patterns
- **[API Reference](../api/reference.md)** - Complete API documentation
