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
- `RoutedClass` mixin enables automatic router discovery and method registration
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

## Calling Handlers

<!-- test: test_router_runtime_extras.py::test_router_call_and_members_structure -->

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

## Dynamic Handler Registration

<!-- test: test_router_basic.py::test_dynamic_router_add_entry_runtime -->

Add handlers programmatically at runtime:

```python
class Dynamic(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

        # Register a lambda
        self.api.add_entry("greet", name="greet")

dyn = Dynamic()

# Add handler at runtime
dyn.api.add_entry(lambda name: f"Hello, {name}", name="greet", replace=True)

# Dynamic handler works immediately
assert dyn.api.get("greet")("World") == "Hello, World"
```

**Use cases**:

- Plugin-provided handlers
- Configuration-driven routing
- Runtime service composition

## Building Hierarchies

<!-- test: test_router_basic.py::test_dotted_path_and_members_with_attached_child -->

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

<!-- test: test_router_basic.py::test_dotted_path_and_members_with_attached_child -->

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

# Get metadata (single source: members)
info = insp.api.members()
assert "action" in info["entries"]
assert "sub" in info["routers"]

# Get members starting from a specific path
sub_info = insp.api.members(basepath="sub")
assert "list" in sub_info["entries"]

# Use lazy=True for on-demand expansion of children
lazy_info = insp.api.members(lazy=True)
assert callable(lazy_info["routers"]["sub"])  # Callable, not expanded
sub_expanded = lazy_info["routers"]["sub"]()  # Expand on demand
```

**`members()` parameters**:

- `basepath`: Start from a specific point in the hierarchy
- `lazy`: Return callables for child routers instead of expanding recursively

**Use `members()` to**:

- Generate API documentation
- Debug routing issues
- Validate configuration
- Build dynamic UIs that expand on demand (with `lazy=True`)

## Next Steps

Now that you understand the basics:

- **[Plugin Guide](plugins.md)** - Extend functionality with plugins
- **[Hierarchies Guide](hierarchies.md)** - Advanced nested routing patterns
- **[Best Practices](best-practices.md)** - Production-ready patterns
- **[API Reference](../api/reference.md)** - Complete API documentation
