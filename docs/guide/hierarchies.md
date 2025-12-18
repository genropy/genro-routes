# Hierarchical Routers

Build complex routing structures with nested routers, dotted path navigation, and automatic plugin inheritance.

## Overview

Genro Routes supports hierarchical router composition where:

- **Parent routers** can have **child routers** attached through explicit instance binding
- **Path separator** `/` navigates the hierarchy (`root.api.get("users/list")`)
- **Plugins propagate** from parent to children automatically
- **Each level** maintains independent handler registration
- **Parent tracking** maintains the relationship between parent and child instances
- **Automatic cleanup** when child instances are replaced

## Managing Hierarchies

Genro Routes provides explicit methods for managing RoutedClass hierarchies:

- **`attach_instance(child, name=...)`** - Attach a RoutedClass instance to create parent-child relationship
- **`detach_instance(child)`** - Remove a RoutedClass instance from the hierarchy
- **Parent tracking** - Children track their parent via `_routed_parent` attribute
- **Auto-detachment** - Replacing a child attribute automatically detaches the old instance

## Basic Instance Attachment

<!-- test: test_router_edge_cases.py::test_attach_and_detach_instance_single_router_with_alias -->

Attach a child instance explicitly with an alias:

```python
from genro_routes import RoutedClass, Router, route

class Child(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list(self):
        return "child:list"

class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        # Store child as attribute first
        self.child = Child()

parent = Parent()

# Attach child's router with custom alias
parent.api.attach_instance(parent.child, name="sales")

# Access through hierarchy
assert parent.api.get("sales/list")() == "child:list"

# get() can also return the child router directly
child_router = parent.api.get("sales")
assert child_router is not None
assert child_router.name == "api"

# Parent tracking is automatic
assert parent.child._routed_parent is parent

# Detach when needed
parent.api.detach_instance(parent.child)
assert parent.child._routed_parent is None
```

**Key requirements**:

- Child must be stored as a parent attribute **before** calling `attach_instance()`
- The `name` parameter provides the alias for accessing the child's router
- Parent tracking is handled automatically
- Detachment clears the parent reference

**`get()` return values**:

- Returns a **callable** if the path points to a handler
- Returns a **Router** if the path points to a child router
- Returns **None** if nothing is found (no exception raised)

## Multiple Routers: Auto-Mapping

<!-- test: test_router_edge_cases.py::test_attach_instance_multiple_routers_requires_mapping -->

When a child has multiple routers, they can be auto-mapped:

```python
class MultiRouterChild(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.admin = Router(self, name="admin")

    @route("api")
    def get_data(self):
        return "data"

    @route("admin")
    def manage(self):
        return "manage"

class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.child = MultiRouterChild()

parent = Parent()

# Auto-map both routers (when parent has single router)
parent.api.attach_instance(parent.child)

# Both child routers are accessible
assert parent.api.get("api/get_data")() == "data"
assert parent.api.get("admin/manage")() == "manage"
```

**Auto-mapping rules**:

- Works when parent has a **single router**
- Child router names become the hierarchy keys
- All child routers are attached automatically
- No explicit mapping needed

## Multiple Routers: Explicit Mapping

<!-- test: test_router_edge_cases.py::test_attach_instance_allows_partial_mapping_and_skips_unmapped -->

Use explicit mapping to control which routers attach and with what aliases:

```python
parent = Parent()
parent.child = MultiRouterChild()

# Attach only the api router with custom alias
parent.api.attach_instance(parent.child, name="api:sales_api")
assert "sales_api" in parent.api._children
assert "admin" not in parent.api._children  # not attached

# Attach both with custom aliases
parent.api.attach_instance(parent.child, name="api:sales, admin:admin_panel")
assert parent.api.get("sales/get_data")() == "data"
assert parent.api.get("admin_panel/manage")() == "manage"
```

**Mapping syntax**:

- Format: `"child_router:parent_alias"`
- Comma-separated for multiple routers
- Unmapped routers are not attached
- Useful for selective exposure

## Parent with Multiple Routers

<!-- test: test_router_edge_cases.py::test_attach_instance_single_child_requires_alias_when_parent_multi -->

When parent has multiple routers, explicit alias is required:

```python
class MultiRouterParent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.admin = Router(self, name="admin")
        self.child = Child()

parent = MultiRouterParent()

# Must provide alias when parent has multiple routers
parent.api.attach_instance(parent.child, name="child_alias")
assert "child_alias" in parent.api._children
```

**Reason**: Prevents ambiguity about which router the child belongs to.

## Branch Routers

<!-- test: test_router_edge_cases.py::test_branch_router_blocks_auto_discover_and_entries -->

Create pure organizational nodes with branch routers:

```python
class OrganizedService(RoutedClass):
    def __init__(self):
        # Branch router: pure container, no handlers
        self.api = Router(self, name="api", branch=True)

        # Add handler routers as children
        self.users = UserService()
        self.products = ProductService()

        self.api.attach_instance(self.users, name="users")
        self.api.attach_instance(self.products, name="products")

service = OrganizedService()

# Access through branch
service.api.get("users/list")()
service.api.get("products/create")()
```

**Branch router characteristics**:

- **Cannot register handlers** - No `@route` methods allowed
- **Pure containers** - Only for organizing child routers
- **Useful for** - API namespacing and logical grouping

**When to use branches**:

```python
# Good: Organize related services under /api namespace
self.api = Router(self, name="api", branch=True)
self.api.attach_instance(self.auth, name="auth")
self.api.attach_instance(self.users, name="users")
# Routes: api.auth.login, api.users.list

# Not needed: Single level with handlers
self.api = Router(self, name="api")  # Regular router
```

## Direct Router Hierarchies with parent_router

<!-- test: test_router_edge_cases.py::test_parent_router_creates_hierarchy -->

Create router hierarchies directly without separate `RoutedClass` instances using `parent_router`:

```python
class Service(RoutedClass):
    def __init__(self):
        # Parent branch router
        self.api = Router(self, name="api", branch=True)

        # Child routers attached via parent_router parameter
        self.users = Router(self, name="users", parent_router=self.api)
        self.orders = Router(self, name="orders", parent_router=self.api)

    @route("users")
    def list_users(self):
        return ["alice", "bob"]

    @route("orders")
    def list_orders(self):
        return ["order1", "order2"]

svc = Service()

# Access through hierarchy
assert svc.api.call("users.list_users") == ["alice", "bob"]
assert svc.api.call("orders.list_orders") == ["order1", "order2"]
```

**Key characteristics**:

- **Same instance**: All routers share the same owner instance
- **Automatic attachment**: Child registers itself in parent's `_children` dict
- **Plugin inheritance**: `_on_attached_to_parent()` is called for plugin propagation
- **Name required**: Child router must have a `name` (used as the hierarchy key)
- **Collision detection**: Raises `ValueError` if name already exists in parent

**When to use `parent_router` vs `attach_instance`**:

| Use Case | Method |
|----------|--------|
| Same instance, multiple routers | `parent_router` |
| Different `RoutedClass` instances | `attach_instance` |
| Dynamic attachment/detachment | `attach_instance` |
| Static hierarchy at init time | `parent_router` |

**Example: Mixed hierarchy**:

```python
class Application(RoutedClass):
    def __init__(self):
        # Root branch
        self.api = Router(self, name="api", branch=True)

        # Direct children via parent_router
        self.users = Router(self, name="users", parent_router=self.api)
        self.products = Router(self, name="products", parent_router=self.api)

        # External service via attach_instance
        self.auth_service = AuthService()
        self.api.attach_instance(self.auth_service, name="auth")

    @route("users")
    def list_users(self):
        return ["alice", "bob"]

    @route("products")
    def list_products(self):
        return ["widget", "gadget"]

app = Application()

# All accessible through hierarchy
app.api.call("users/list_users")      # Direct child
app.api.call("products/list_products") # Direct child
app.api.call("auth/login")            # Attached instance
```

## Auto-Detachment

<!-- test: test_router_edge_cases.py::test_auto_detach_on_attribute_replacement -->

Replacing a child attribute automatically detaches the old instance:

```python
class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.child = Child()
        self.api.attach_instance(self.child, name="child")

parent = Parent()
assert parent.child._routed_parent is parent
assert "child" in parent.api._children

# Replacing the attribute triggers auto-detach
parent.child = None

# Old child is automatically removed from hierarchy
assert "child" not in parent.api._children
```

**Auto-detachment behavior**:

- Triggered when setting `parent.attribute = new_value`
- Only detaches if old value's `_routed_parent` is this parent
- Clears `_routed_parent` on detached instance
- Removes from all parent routers automatically
- Best-effort: ignores errors to avoid blocking attribute assignment

**Use cases**:

```python
# Replacing a service implementation
parent.auth_service = OldAuthService()
parent.api.attach_instance(parent.auth_service, name="auth")

# Later: automatic cleanup
parent.auth_service = NewAuthService()  # Old service auto-detached
parent.api.attach_instance(parent.auth_service, name="auth")
```

## Parent Tracking

Every attached RoutedClass tracks its parent:

```python
class Child(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    def get_parent_info(self):
        if self._routed_parent:
            return f"My parent is {type(self._routed_parent).__name__}"
        return "No parent"

child = Child()
assert child._routed_parent is None  # Not attached

parent = Parent()
parent.child = child
parent.api.attach_instance(parent.child, name="child")
assert child._routed_parent is parent  # Parent tracked

parent.api.detach_instance(child)
assert child._routed_parent is None  # Cleared on detach
```

**Parent tracking enables**:

- Context awareness in child methods
- Access to parent's state and configuration
- Proper cleanup on detachment
- Preventing duplicate attachments

## Plugin Inheritance

<!-- test: test_router_runtime_extras.py::test_inherit_plugins_branches -->

Plugins propagate automatically from parent to children:

```python
class Service(RoutedClass):
    def __init__(self, name: str):
        self.name = name
        self.api = Router(self, name="api")

    @route("api")
    def process(self):
        return f"{self.name}:process"

class Application(RoutedClass):
    def __init__(self):
        # Plugin attached to parent
        self.api = Router(self, name="api").plug("logging")
        self.service = Service("main")

app = Application()

# Attach child - plugins inherit automatically
app.api.attach_instance(app.service, name="service")

# Child router has the logging plugin
assert hasattr(app.service.api, "logging")

# Plugin applies to child handlers
result = app.service.api.get("process")()
# Logging plugin was active during call
```

**Inheritance rules**:

- Parent plugins apply to all child handlers
- Children can add their own plugins
- Plugin order: parent plugins -> child plugins
- Configuration inherits but can be overridden

## Dotted Path Navigation

<!-- test: test_router_edge_cases.py::test_routed_proxy_get_router_handles_dotted_path -->

Navigate hierarchy with dotted paths via `routedclass.get_router()`:

```python
class Child(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.child = Child()
        self.api.attach_instance(self.child, name="child")

parent = Parent()

# Get child router directly
child_router = parent.routedclass.get_router("api/child")
assert child_router.name == "api"
assert child_router.instance is parent.child
```

**Navigation features**:

- `get_router("router/child/grandchild")` traverses hierarchy
- Returns the target router instance
- Enables programmatic router access
- Useful for dynamic configuration

## Introspection

<!-- test: test_router_basic.py::test_dotted_path_and_nodes_with_attached_child -->

Inspect the full hierarchy structure:

```python
class Inspectable(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.service = Service("child")
        self.api.attach_instance(self.service, name="sub")

    @route("api")
    def action(self):
        pass

insp = Inspectable()

# Get complete hierarchy metadata
info = insp.api.nodes()
assert "action" in info["entries"]
assert "sub" in info["routers"]

# Child routers included
child_info = info["routers"]["sub"]
assert child_info["name"] == "api"

# Get nodes starting from a child
sub_only = insp.api.nodes(basepath="sub")
assert "list" in sub_only["entries"]

# Lazy mode: children are callables
lazy = insp.api.nodes(lazy=True)
assert callable(lazy["routers"]["sub"])
sub_expanded = lazy["routers"]["sub"]()  # Expand on demand
```

**`nodes()` parameters**:

- `basepath`: Start from a specific point in the hierarchy (e.g., `"child/grandchild"`)
- `lazy`: Return callables for child routers instead of expanding recursively
- `mode`: Output format mode (e.g., `"openapi"` for OpenAPI schema generation)

```python
# Generate OpenAPI schema for the hierarchy
schema = insp.api.nodes(mode="openapi")
# Or use the shortcut
schema = insp.api.openapi()
```

**Introspection provides**:

- Complete handler list at each level
- Child router names and structure
- Plugin configuration per level
- Nested hierarchy representation
- On-demand expansion with `lazy=True`
- OpenAPI schema generation with `mode="openapi"`

## Catch-All Routes with `default_entry`

<!-- test: test_router_basic.py::TestDefaultEntryWithPartial -->

When using `partial=True`, routers can handle paths that don't fully resolve by delegating to a `default_entry` handler:

```python
class FileService(RoutedClass):
    def __init__(self):
        # default_entry="index" is the default
        self.api = Router(self, name="api")

    @route("api")
    def index(self, *path_segments):
        return f"File: {'/'.join(path_segments)}"

class Application(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.files = FileService()
        self.api.attach_instance(self.files, name="files")

app = Application()

# Path "files/docs/readme.md" - "files" is a child router,
# "docs/readme.md" doesn't exist, so partial=True uses default_entry
result = app.api.get("files/docs/readme.md", partial=True)
# Returns: functools.partial(files.index, "docs", "readme.md")
assert result() == "File: docs/readme.md"
```

**Behavior by scenario**:

| Path | Scenario | Result with `partial=True` |
|------|----------|---------------------------|
| `child/handler` | Handler exists | Returns handler directly |
| `child/unknown/path` | Child exists, path unresolved | `partial(child.default_entry, "unknown", "path")` |
| `child` (router) | Single segment, is router | `partial(child.default_entry)` |
| `unknown/path` | Nothing found | Uses this router's `default_entry` |

**Custom `default_entry`**:

```python
class CustomService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api", default_entry="catch_all")

    @route("api")
    def catch_all(self, *args):
        return f"Caught: {args}"
```

**Error handling**:

If `default_entry` handler doesn't exist in the target router, `ValueError` is raised:

```python
class EmptyService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")  # No "index" entry!

svc = EmptyService()
svc.api.get("unknown/path", partial=True)  # ValueError!
```

## Real-World Examples

### Microservice-Style Organization

```python
class AuthService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def login(self, username: str, password: str):
        return {"token": "..."}

    @route("api")
    def logout(self, token: str):
        return {"status": "ok"}

class UserService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list_users(self):
        return ["alice", "bob"]

    @route("api")
    def get_user(self, user_id: int):
        return {"id": user_id, "name": "..."}

class Application(RoutedClass):
    def __init__(self):
        # Root router with logging
        self.api = Router(self, name="api").plug("logging")

        # Create services
        self.auth = AuthService()
        self.users = UserService()

        # Attach to hierarchy
        self.api.attach_instance(self.auth, name="auth")
        self.api.attach_instance(self.users, name="users")

app = Application()

# Access through hierarchy
token = app.api.call("auth/login", "alice", "secret123")
users = app.api.call("users/list_users")

# Logging applies to all handlers automatically
```

### Multi-Level Organization with Branches

```python
class ReportsAPI(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def sales_report(self):
        return "sales data"

    @route("api")
    def inventory_report(self):
        return "inventory data"

class AdminAPI(RoutedClass):
    def __init__(self):
        # Branch for organization
        self.api = Router(self, name="api", branch=True)

        self.users = UserService()
        self.reports = ReportsAPI()

        self.api.attach_instance(self.users, name="users")
        self.api.attach_instance(self.reports, name="reports")

class Application(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api", branch=True)

        # Public API
        self.public = UserService()  # Simplified public interface

        # Admin API (protected, more capabilities)
        self.admin = AdminAPI()

        self.api.attach_instance(self.public, name="public")
        self.api.attach_instance(self.admin, name="admin")

app = Application()

# Clean hierarchy
app.api.get("public/list_users")()           # Public access
app.api.get("admin/users/get_user")(123)     # Admin user access
app.api.get("admin/reports/sales_report")()  # Admin reports
```

### Dynamic Service Replacement

```python
class ServiceV1(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def process(self, data: str):
        return f"v1:{data}"

class ServiceV2(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def process(self, data: str):
        return f"v2:{data}"

class Application(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.service = ServiceV1()
        self.api.attach_instance(self.service, name="processor")

    def upgrade_service(self):
        # Auto-detachment happens here
        self.service = ServiceV2()
        self.api.attach_instance(self.service, name="processor")

app = Application()
assert app.api.get("processor/process")("test") == "v1:test"

app.upgrade_service()  # Seamless replacement
assert app.api.get("processor/process")("test") == "v2:test"
```

## Best Practices

### Logical Grouping with Branches

```python
# Use branch routers for pure organization
class API(RoutedClass):
    def __init__(self):
        self.root = Router(self, name="root", branch=True)

        # Group related services
        self.auth = AuthService()
        self.users = UserService()
        self.orders = OrderService()

        self.root.attach_instance(self.auth, name="auth")
        self.root.attach_instance(self.users, name="users")
        self.root.attach_instance(self.orders, name="orders")
```

### Shared Plugins at Root

```python
# Apply common plugins to entire hierarchy
self.api = Router(self, name="api")\
    .plug("logging")\
    .plug("pydantic")

# All children inherit both plugins
self.api.attach_instance(self.auth, name="auth")
self.api.attach_instance(self.users, name="users")
```

### Deep Hierarchies

```python
# Organize by domain and subdomain
app.api.attach_instance(self.admin, name="admin")
admin.api.attach_instance(self.user_admin, name="users")
admin.api.attach_instance(self.report_admin, name="reports")

# Access: app.api.get("admin/users/create_user")
#         app.api.get("admin/reports/sales_report")
```

### Store Before Attach

```python
# REQUIRED: Always store child as attribute first
class Parent(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.child = Child()  # Store first
        self.api.attach_instance(self.child, name="child")  # Then attach
```

### Explicit Detachment

```python
# Explicit detachment for clarity
if should_remove_service:
    self.api.detach_instance(self.old_service)
    self.old_service = None  # Clear reference
```

### Prevent Name Collisions

```python
# Use descriptive aliases
self.api.attach_instance(self.auth, name="auth_v1")
self.api.attach_instance(self.new_auth, name="auth_v2")

# Access both versions
self.api.get("auth_v1/login")
self.api.get("auth_v2/login")
```

## Common Patterns

### Parent-Aware Children

```python
class ChildService(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def get_config(self):
        # Access parent context
        if self._routed_parent:
            return self._routed_parent.config
        return {}
```

### Conditional Attachment

```python
class Application(RoutedClass):
    def __init__(self, config):
        self.api = Router(self, name="api")

        # Attach based on configuration
        if config.get("enable_auth"):
            self.auth = AuthService()
            self.api.attach_instance(self.auth, name="auth")

        if config.get("enable_admin"):
            self.admin = AdminService()
            self.api.attach_instance(self.admin, name="admin")
```

### Multi-Router Services

```python
class DualInterfaceService(RoutedClass):
    def __init__(self):
        self.public = Router(self, name="public")
        self.admin = Router(self, name="admin")

    @route("public")
    def public_endpoint(self):
        return "public data"

    @route("admin")
    def admin_endpoint(self):
        return "admin data"

# Attach with mapping
parent.api.attach_instance(service, name="public:api, admin:admin_api")
```

## Next Steps

- **[Plugin Configuration](plugin-configuration.md)** - Configure plugins across hierarchies
- **[Best Practices](best-practices.md)** - Production-ready patterns
- **[API Reference](../api/reference.md)** - Complete API documentation
