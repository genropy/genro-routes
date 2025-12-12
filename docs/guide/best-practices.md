# Best Practices

This guide covers production-tested patterns and anti-patterns for Genro Routes.

## Router Design

### Keep Routers Focused

Each router should have a clear, single responsibility:

```python
# Good: Focused routers
class UserService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list_users(self): ...

    @route("api")
    def get_user(self, user_id: int): ...

    @route("api")
    def create_user(self, data: dict): ...


# Bad: Router doing too much
class EverythingService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list_users(self): ...

    @route("api")
    def send_email(self): ...

    @route("api")
    def generate_report(self): ...
```

### Use Meaningful Names

Router and handler names should be self-documenting:

```python
# Good: Clear, descriptive names
class OrderService(RoutedClass):
    def __init__(self):
        self.orders = Router(self, name="orders")

    @route("orders")
    def list_pending(self): ...

    @route("orders")
    def mark_shipped(self, order_id: int): ...


# Bad: Vague names
class Service(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def do_stuff(self): ...

    @route("api")
    def process(self, id): ...
```

### Leverage Prefixes for Organization

Use prefixes to group related handlers while keeping public names clean:

```python
class AdminAPI(RoutedClass):
    def __init__(self):
        self.admin = Router(self, name="admin", prefix="admin_")

    @route("admin")
    def admin_list_users(self):
        """Exposed as 'list_users'"""
        ...

    @route("admin")
    def admin_delete_user(self, user_id: int):
        """Exposed as 'delete_user'"""
        ...
```

## Hierarchy Design

### Flat is Better Than Deep

Prefer shallow hierarchies over deeply nested ones:

```python
# Good: Shallow, navigable hierarchy
app.api.get("users.list")
app.api.get("orders.create")
app.api.get("reports.sales")

# Bad: Too deep, hard to navigate
app.api.get("v1.internal.services.users.management.list")
```

### Use Branch Routers for Organization

Branch routers provide namespace organization without handlers:

```python
class Application(RoutedClass):
    def __init__(self):
        # Branch router as namespace container
        self.api = Router(self, name="api", branch=True, auto_discover=False)

        # Attach actual services
        self.api.attach_instance(self.users, name="users")
        self.api.attach_instance(self.orders, name="orders")
```

### Store Before Attach

Always store child instances as attributes before attaching:

```python
# Good: Store then attach
class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.child = ChildService()  # Store first
        self.api.attach_instance(self.child, name="child")  # Then attach


# Bad: Attach without storing
class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.api.attach_instance(ChildService(), name="child")  # Will fail!
```

## Plugin Usage

### Apply Plugins at the Right Level

Attach plugins where they make sense:

```python
# Good: Logging at root, validation where needed
class Application(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("logging")  # All handlers logged

        self.public = PublicAPI()  # No validation needed
        self.admin = AdminAPI()    # Has its own pydantic plugin

        self.api.attach_instance(self.public, name="public")
        self.api.attach_instance(self.admin, name="admin")


class AdminAPI(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("pydantic")  # Strict validation
```

### Compose Simple Plugins

Multiple focused plugins beat one complex plugin:

```python
# Good: Composable plugins
self.api = Router(self, name="api")\
    .plug("logging")\
    .plug("pydantic")\
    .plug("caching")

# Bad: Monolithic plugin
self.api = Router(self, name="api").plug("do_everything")
```

### Configure Plugins Explicitly

Don't rely on defaults for production:

```python
# Good: Explicit configuration
svc.routedclass.configure("api:logging/_all_", level="info", enabled=True)
svc.routedclass.configure("api:pydantic/_all_", strict=True)

# Bad: Implicit defaults everywhere
svc.api.plug("logging").plug("pydantic")  # What's the config?
```

## Error Handling

### Let Errors Propagate

Don't swallow exceptions in handlers:

```python
# Good: Let errors propagate
@route("api")
def create_user(self, data: dict):
    user = self.repository.create(data)  # May raise
    return user


# Bad: Swallowing errors
@route("api")
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
    result = svc.api.get("list_users")()
    assert isinstance(result, list)

def test_user_service_create():
    svc = UserService()
    result = svc.api.call("create_user", {"name": "Alice"})
    assert result["name"] == "Alice"
```

### Test Hierarchies

Verify hierarchy structure and access:

```python
def test_application_hierarchy():
    app = Application()

    # Verify structure
    members = app.api.members()
    assert "users" in members["routers"]
    assert "orders" in members["routers"]

    # Verify access
    users = app.api.get("users.list_users")()
    assert isinstance(users, list)
```

### Test Plugin Behavior

Test that plugins affect handler execution:

```python
def test_logging_plugin_called(caplog):
    svc = LoggedService()
    svc.api.get("action")()

    assert "action" in caplog.text
```

## Performance

### Avoid Rebuilding Handlers

Handler tables rebuild on plugin attachment. Attach plugins before adding handlers:

```python
# Good: Plugins first
class Service(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")\
            .plug("logging")\
            .plug("pydantic")
        # Handlers auto-discovered after plugins


# Bad: Adding plugins after runtime entries
class Service(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    def late_init(self):
        self.api.add_entry(handler, name="late")
        self.api.plug("logging")  # Rebuilds all handlers!
```

### Cache Handler References

If calling the same handler repeatedly, cache the reference:

```python
# Good: Cache for repeated calls
handler = svc.api.get("process")
for item in items:
    handler(item)

# Less efficient: Lookup every time
for item in items:
    svc.api.get("process")(item)
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
class A(RoutedClass):
    def __init__(self, b):
        self.api = Router(self, name="api")
        self.b = b
        self.api.attach_instance(b, name="b")

class B(RoutedClass):
    def __init__(self, a):
        self.api = Router(self, name="api")
        self.a = a
        self.api.attach_instance(a, name="a")  # Circular!
```

### Over-Configuration

Don't configure what doesn't need configuration:

```python
# Bad: Over-engineered
svc.routedclass.configure("api:logging/handler1", level="info")
svc.routedclass.configure("api:logging/handler2", level="info")
svc.routedclass.configure("api:logging/handler3", level="info")
# ... 50 more lines

# Good: Use defaults and override exceptions
svc.routedclass.configure("api:logging/_all_", level="info")
svc.routedclass.configure("api:logging/debug_*", level="debug")
```

## Summary

| Do | Don't |
|----|-------|
| Keep routers focused | Mix unrelated handlers |
| Use meaningful names | Use vague names |
| Store before attach | Attach anonymous instances |
| Apply plugins at right level | Over-apply plugins |
| Let errors propagate | Swallow exceptions |
| Test handlers in isolation | Only test via HTTP |
| Cache handler references | Lookup repeatedly |
| Use per-instance state | Use global state |

## Next Steps

- **[API Reference](../api/reference.md)** - Complete API documentation
- **[Plugin Development](plugins.md)** - Create custom plugins
- **[Hierarchies](hierarchies.md)** - Advanced routing patterns
