# Best Practices

This guide covers production-tested patterns and anti-patterns for Genro Routes.

## Router Design

### Keep Services Focused

Each RoutingClass should have a clear, single responsibility. A class with
no plugins or router options needs no `__init__` at all:

```python
# Good: Focused service
class UserService(RoutingClass):
    @route()
    def list_users(self): ...

    @route()
    def get_user(self, user_id: int): ...

    @route()
    def create_user(self, data: dict): ...


# Bad: Service doing too much
class EverythingService(RoutingClass):
    @route()
    def list_users(self): ...

    @route()
    def send_email(self): ...

    @route()
    def generate_report(self): ...
```

### Use Meaningful Names

Handler names and attachment aliases should be self-documenting:

```python
# Good: Clear, descriptive names
class OrderService(RoutingClass):
    @route()
    def list_pending(self): ...

    @route()
    def mark_shipped(self, order_id: int): ...


# Bad: Vague names
class Service(RoutingClass):
    @route()
    def do_stuff(self): ...

    @route()
    def process(self, id): ...
```

### Leverage Prefixes for Organization

Use prefixes to group related handlers while keeping public names clean:

```python
class AdminAPI(RoutingClass):
    def __init__(self):
        self.route.prefix = "admin_"

    @route()
    def admin_list_users(self):
        """Exposed as 'list_users'"""
        ...

    @route()
    def admin_delete_user(self, user_id: int):
        """Exposed as 'delete_user'"""
        ...
```

## Hierarchy Design

### Flat is Better Than Deep

Prefer shallow hierarchies over deeply nested ones:

```python
# Good: Shallow, navigable hierarchy
app.route.node("users/list")()
app.route.node("orders/create")()
app.route.node("reports/sales")()

# Bad: Too deep, hard to navigate
app.route.node("v1/internal/services/users/management/list")()
```

### Use Sections for Organization

A `Section` is an empty RoutingClass that provides namespace organization
without handlers:

```python
from genro_routes import RoutingClass, Section

class Application(RoutingClass):
    def __init__(self):
        # Section as a namespace container
        admin = Section("Admin area")
        self.attach_instance(admin, name="admin")

        # Attach actual services under the section
        admin.attach_instance(UserAdmin(), name="users")
        admin.attach_instance(OrderAdmin(), name="orders")
```

### Attaching Child Instances

Child instances can be attached directly — storing as an attribute is optional:

```python
class Parent(RoutingClass):
    def __init__(self):
        # Both approaches work — the router tree keeps a strong reference
        self.attach_instance(ChildService(), name="child")

# Retrieve the child instance later if needed
child = parent.routing.instance("child")
```

## Plugin Usage

### Apply Plugins at the Right Level

Attach plugins where they make sense:

```python
# Good: Logging at root, validation where needed
class Application(RoutingClass):
    def __init__(self):
        self.route.plug("logging")  # All handlers logged

        self.public = PublicAPI()  # No validation needed
        self.admin = AdminAPI()    # Has its own pydantic plugin

        self.attach_instance(self.public, name="public")
        self.attach_instance(self.admin, name="admin")


class AdminAPI(RoutingClass):
    def __init__(self):
        self.route.plug("pydantic")  # Strict validation
```

### Compose Simple Plugins

Multiple focused plugins beat one complex plugin:

```python
# Good: Composable plugins
self.route.plug("logging")\
    .plug("pydantic")\
    .plug("caching")

# Bad: Monolithic plugin
self.route.plug("do_everything")
```

### Configure Plugins Explicitly

Don't rely on defaults for production:

```python
# Good: Explicit configuration
svc.routing.configure("logging/_all_", enabled=True, log=True)
svc.routing.configure("pydantic/_all_", disabled=False)

# Bad: Implicit defaults everywhere
svc.route.plug("logging").plug("pydantic")  # What's the config?
```

## Error Handling

### Let Errors Propagate

Don't swallow exceptions in handlers:

```python
# Good: Let errors propagate
@route()
def create_user(self, data: dict):
    user = self.repository.create(data)  # May raise
    return user


# Bad: Swallowing errors
@route()
def create_user(self, data: dict):
    try:
        user = self.repository.create(data)
        return user
    except Exception:
        return None  # Caller has no idea what happened
```

### Use Plugin Wrappers for Cross-Cutting Concerns

Handle errors consistently via plugins:

```python
class ErrorHandlerPlugin(BasePlugin):
    plugin_code = "error_handler"
    plugin_description = "Consistent error handling"

    def wrap_handler(self, router, entry, call_next):
        def wrapper(*args, **kwargs):
            try:
                return call_next(*args, **kwargs)
            except ValidationError as e:
                return {"error": "validation", "details": str(e)}
            except NotFoundError as e:
                return {"error": "not_found", "details": str(e)}
        return wrapper
```

## Testing

### Test Handlers in Isolation

Test handler logic independently of routing:

```python
def test_user_service_list():
    svc = UserService()
    # Test via router
    result = svc.route.node("list_users")()
    assert isinstance(result, list)

def test_user_service_create():
    svc = UserService()
    result = svc.route.node("create_user")({"name": "Alice"})
    assert result["name"] == "Alice"
```

### Test Hierarchies

Verify hierarchy structure and access:

```python
def test_application_hierarchy():
    app = Application()

    # Verify structure
    nodes = app.route.nodes()
    assert "users" in nodes["routers"]
    assert "orders" in nodes["routers"]

    # Verify access
    users = app.route.node("users/list_users")()
    assert isinstance(users, list)
```

### Test Plugin Behavior

Test that plugins affect handler execution:

```python
def test_logging_plugin_called(caplog):
    svc = LoggedService()
    svc.route.node("action")()

    assert "action" in caplog.text
```

## Performance

### Attach Plugins Early

Attach plugins during router creation for optimal handler wrapping:

```python
# Good: Plugins attached during construction
class Service(RoutingClass):
    def __init__(self):
        self.route.plug("logging").plug("pydantic")

    @route()
    def action(self):
        return "done"
```

### Cache Handler References

If calling the same handler repeatedly, cache the reference:

```python
# Good: Cache for repeated calls
node = svc.route.node("process")
for item in items:
    node(item)

# Less efficient: Lookup every time
for item in items:
    svc.route.node("process")(item)
```

## Anti-Patterns

### Global State in Plugins

Plugins should not share global state:

```python
# Bad: Global state
_global_cache = {}

class CachePlugin(BasePlugin):
    def wrap_handler(self, router, entry, call_next):
        def wrapper(*args):
            key = (entry.name, args)
            if key in _global_cache:  # Shared across all instances!
                return _global_cache[key]
            ...


# Good: Per-instance state
class CachePlugin(BasePlugin):
    __slots__ = ("_cache",)

    def __init__(self, router, **config):
        self._cache = {}  # Per-instance
        super().__init__(router, **config)
```

### Circular Dependencies

Avoid circular attachments:

```python
# Bad: Circular reference
class A(RoutingClass):
    def __init__(self, b):
        self.b = b
        self.attach_instance(b, name="b")

class B(RoutingClass):
    def __init__(self, a):
        self.a = a
        self.attach_instance(a, name="a")  # Circular!
```

### Over-Configuration

Don't configure what doesn't need configuration:

```python
# Bad: Over-engineered
svc.routing.configure("logging/handler1", log=True)
svc.routing.configure("logging/handler2", log=True)
svc.routing.configure("logging/handler3", log=True)
# ... 50 more lines

# Good: Use defaults and override exceptions
svc.routing.configure("logging/_all_", log=True)
svc.routing.configure("logging/debug_*", print=True)
```

## Summary

| Do | Don't |
|----|-------|
| Keep services focused | Mix unrelated handlers |
| Use meaningful names | Use vague names |
| Use `routing.instance()` to retrieve children | Rely on global variables for child access |
| Apply plugins at right level | Over-apply plugins |
| Let errors propagate | Swallow exceptions |
| Test handlers in isolation | Only test via HTTP |
| Cache handler references | Lookup repeatedly |
| Use per-instance state | Use global state |

## Next Steps

- **[API Reference](../api/reference.md)** - Complete API documentation
- **[Plugin Development](plugins.md)** - Create custom plugins
- **[Hierarchies](hierarchies.md)** - Advanced routing patterns
