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

**Key points**:

- `Router(self, name="api")` creates instance-scoped router in `__init__`
- `@route("api")` marks method for registration
- `RoutingClass` is **required** - all classes using `Router` must inherit from it
- Each instance has independent routing state

## Registering Handlers

<!-- test: test_router_edge_cases.py::test_router_auto_registers_marked_methods_and_validates_plugins -->

Methods are automatically registered when decorated with `@route`:

```python
class API(RoutingClass):
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
assert api.routes.node("echo")("hello") == "hello"

# Custom name resolution
assert api.routes.node("alt_name")() == "executed"
```

**Registration happens automatically** when you inherit from `RoutingClass` and instantiate routers in `__init__`.

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

    @route()  # Also uses the single router
    def remove(self, id):
        return f"removed:{id}"

t = Table()
assert t.table.node("add")("x") == "added:x"
assert t.table.node("remove")(1) == "removed:1"
```

**Rules**:

- If the class has exactly one router: `@route()` works without arguments
- If the class has multiple routers: `@route()` requires an explicit router name

### Accessing the Default Router

You can access the default router programmatically via the `default_router` property:

```python
class SingleAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route()
    def ping(self):
        return "pong"

svc = SingleAPI()
assert svc.default_router is svc.api  # Only one router = default

class MultiAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.admin = Router(self, name="admin")

m = MultiAPI()
assert m.default_router is None  # Multiple routers = no default
```

## Calling Handlers

<!-- test: test_router_runtime_extras.py::test_router_node_and_nodes_structure -->

Use `node()` to retrieve handlers - it returns a callable `RouterNode`:

```python
class Calculator(RoutingClass):
    def __init__(self):
        self.ops = Router(self, name="ops")

    @route("ops")
    def add(self, a: int, b: int):
        return a + b

calc = Calculator()

# node() returns a RouterNode which is callable
node = calc.ops.node("add")
assert node(2, 3) == 5

# RouterNode also provides metadata access
assert node.name == "add"
assert node.type == "entry"
assert node.is_entry
```

**RouterNode features**:

- Callable: invoke directly with `node(*args, **kwargs)`
- Boolean: `if node:` returns `True` if node exists
- Metadata: access `node.name`, `node.type`, `node.metadata`, `node.doc`
- Authorization: check `node.is_callable` and `node.error` before calling

## Using Prefixes and Custom Names

<!-- test: test_router_basic.py::test_prefix_and_name_override -->

Clean up method names with prefixes and provide alternative names with the `name` option:

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

**Benefits**:

- Prefixes keep method names organized in code
- Explicit names provide cleaner external APIs
- Router resolves both automatically

## Checking Node Existence

<!-- test: test_router_runtime_extras.py::test_node_returns_child_router -->

Use the boolean value of `RouterNode` to check if a path exists:

```python
class Fallback(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def known_action(self):
        return "success"

fb = Fallback()

# Existing handler - node is truthy
node = fb.api.node("known_action")
if node:
    assert node() == "success"

# Non-existing - node is falsy (empty RouterNode)
missing = fb.api.node("missing")
if not missing:
    print("Handler not found")
assert missing == {}  # Empty RouterNode equals empty dict
```

**RouterNode boolean behavior**:

- Truthy if node exists (has a `type`)
- Falsy if path doesn't resolve to anything
- Empty `RouterNode` compares equal to `{}`

**Note**: `node()` can also return a child router if the path points to one (see [Hierarchies](hierarchies.md)).

## Exceptions: NotFound, NotAuthorized, NotAvailable

<!-- test: test_auth_plugin.py::TestNodeWithFilters -->

Genro Routes provides exceptions for handling routing errors:

```python
from genro_routes import NotFound, NotAuthorized, NotAvailable

# NotFound - raised when calling node() on non-existent entry
# NotAuthorized - raised when entry exists but auth tags don't match
# NotAvailable - raised when entry exists but capabilities are missing
```

**Using `node()` with filters**:

```python
from genro_routes import RoutingClass, Router, route, NotFound, NotAuthorized

class SecureAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("auth")

    @route("api", auth_rule="admin")
    def admin_action(self):
        return "admin only"

    @route("api", auth_rule="public")
    def public_action(self):
        return "public"

api = SecureAPI()

# Entry exists and tag matches - node is callable
node = api.api.node("admin_action", auth_tags="admin")
assert node.is_callable
assert node() == "admin only"

# Entry exists but tag doesn't match - node exists but is not callable
node = api.api.node("admin_action", auth_tags="public")
assert node  # Node exists
assert not node.is_callable  # But not callable
assert node.error == "not_authorized"  # Error reason
# Calling raises NotAuthorized
try:
    node()
except NotAuthorized as e:
    print(f"Access denied: {e.selector}")  # "admin_action"

# Entry doesn't exist - empty node
node = api.api.node("nonexistent")
assert not node  # Falsy - doesn't exist
# Calling raises NotFound
try:
    node()
except NotFound as e:
    print(f"Not found: {e.selector}")  # "nonexistent"
```

**Exception attributes**:

- `selector`: The path that was requested
- `router_name`: The router where the error occurred

**RouterNode properties**:

- `node.is_callable`: Returns `True` if node can be called without error
- `node.error`: Error code string (e.g., `"not_authorized"`, `"not_available"`) or `None`
- Calling a node with error raises the appropriate exception

**Best-match resolution with extra_args**:

The `node()` method uses best-match resolution - it walks the path as far as possible and returns unconsumed segments in `extra_args` and `partial_kwargs`:

```python
node = router.node("unknown/path")
# Returns RouterNode with:
#     type: "entry"
#     name: "index"  # default_entry handler
#     extra_args: ["unknown", "path"]  # positional args
#     partial_kwargs: {}  # keyword args from path segments
result = node()  # calls handler("unknown", "path")
```

## Catch-All Routing with `default_entry`

<!-- test: test_router_basic.py::TestDefaultEntryWithPartial -->

Routers have a `default_entry` parameter (default: `"index"`) that enables catch-all routing patterns via best-match resolution:

```python
class FileServer(RoutingClass):
    def __init__(self):
        # default_entry="index" is the default, but can be customized
        self.api = Router(self, name="api", default_entry="serve")

    @route("api")
    def serve(self, *path_segments):
        return f"Serving: {'/'.join(path_segments)}"

server = FileServer()

# node() uses best-match resolution - when path can't be fully resolved,
# unconsumed segments become arguments via functools.partial
node = server.api.node("docs/api/reference")
# node.callable is: functools.partial(server.serve, "docs", "api", "reference")
# node.partial_args is: ["docs", "api", "reference"]
assert node() == "Serving: docs/api/reference"
```

**Key behaviors**:

- `default_entry` specifies which handler to use for unresolved paths (default: `"index"`)
- Best-match resolution walks the path as far as possible
- Unconsumed path segments are passed as positional arguments via `functools.partial`
- Access unconsumed segments via `node.partial_args`
- If `default_entry` handler doesn't exist, returns empty `RouterNode`

**Use cases**:

- File servers with arbitrary path depth
- Catch-all handlers for dynamic routing
- Pass-through routes to external services

## Building Hierarchies

<!-- test: test_router_basic.py::test_dotted_path_and_nodes_with_attached_child -->

Create nested router structures with dotted path access:

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

**Hierarchies enable**:

- Organized service composition
- Logical grouping of related handlers
- Namespace isolation

## Introspection

<!-- test: test_router_basic.py::test_dotted_path_and_nodes_with_attached_child -->

Inspect router structure and registered handlers:

```python
class Inspectable(RoutingClass):
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

## Custom Metadata with `meta_*`

Add custom metadata to handlers using the `meta_` prefix in `@route()`:

```python
class MetadataAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api", meta_mimetype="application/json", meta_deprecated=True)
    def get_data(self):
        """Return data in JSON format."""
        return {"foo": "bar"}

    @route("api", meta_version="2.0", meta_auth_required=True)
    def get_data_v2(self):
        return {"foo": "bar", "extra": True}

api = MetadataAPI()

# Access metadata via node()
node = api.api.node("get_data")
assert node.metadata["meta"]["mimetype"] == "application/json"
assert node.metadata["meta"]["deprecated"] is True

# Or via nodes() for all entries
all_info = api.api.nodes()
entry_meta = all_info["entries"]["get_data_v2"]["metadata"]["meta"]
assert entry_meta["version"] == "2.0"
assert entry_meta["auth_required"] is True
```

**Key behaviors**:

- `meta_*` kwargs are grouped under `metadata["meta"]` in the entry
- The `meta_` prefix is stripped from the key name
- Works with both `@route()` decorator and `_add_entry()` method
- Separate from plugin configuration (which uses `<plugin>_<key>` format)

**Use cases**:

- API versioning information
- Deprecation markers
- Content-type hints
- Custom authorization requirements
- Any handler-specific metadata not tied to plugins

## Next Steps

Now that you understand the basics:

- **[Plugin Guide](plugins.md)** - Extend functionality with plugins
- **[Hierarchies Guide](hierarchies.md)** - Advanced nested routing patterns
- **[Best Practices](best-practices.md)** - Production-ready patterns
- **[API Reference](../api/reference.md)** - Complete API documentation
