# Auth - Authorization Plugin

**Status**: 🔴 DA REVISIONARE

## Overview

The `AuthPlugin` provides tag-based authorization for router entries. It evaluates
authorization rules defined on endpoints against user tags from the execution context.

## Terminology

| Concept | Location | Description |
|---------|----------|-------------|
| `auth_rule` | `@route(...)` | Authorization rule the endpoint requires |
| `auth_tags` | `nodes()`, `node()` | Tags the current user has (query parameter) |
| `AuthPlugin` | Plugin | Evaluates rules against user tags |

## Usage

### Defining Authorization Rules

```python
from genro_routes import Router, RoutingClass, route

class AdminAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("auth")

    @route("api", auth_rule="admin")
    def delete_user(self, user_id):
        """Only users with 'admin' tag can access."""
        return f"Deleted {user_id}"

    @route("api", auth_rule="admin|manager")
    def view_reports(self):
        """Users with 'admin' OR 'manager' tag can access."""
        return "Reports..."

    @route("api", auth_rule="admin&hr")
    def manage_salaries(self):
        """Users with BOTH 'admin' AND 'hr' tags can access."""
        return "Salaries..."

    @route("api")
    def public_info(self):
        """No auth_rule = public access."""
        return "Public info"
```

### Rule Syntax

**IMPORTANT**: Comma is NOT allowed in `auth_rule`. Use `|` for OR, `&` for AND.

| Syntax | Meaning | Example |
|--------|---------|---------|
| `"admin"` | Single tag required | User must have "admin" |
| `"admin\|hr"` | OR | User must have "admin" OR "hr" |
| `"admin&hr"` | AND | User must have "admin" AND "hr" |
| `"!guest"` | NOT | User must NOT have "guest" |
| `"(admin\|manager)&!suspended"` | Complex | Admin or manager, not suspended |

Keywords `and`, `or`, `not` are also supported (case-insensitive):

- `"admin or manager"` is equivalent to `"admin|manager"`
- `"admin and hr"` is equivalent to `"admin&hr"`
- `"not guest"` is equivalent to `"!guest"`

### Runtime Filtering

```python
api = AdminAPI()

# Filter visible entries by user tags (comma = user has multiple tags)
api.api.nodes(auth_tags="admin")           # user has 'admin' tag
api.api.nodes(auth_tags="admin,manager")   # user has both 'admin' AND 'manager' tags

# Access control on node/call
handler = api.api.node("delete_user", auth_tags="admin")  # raises NotAuthorized if filtered
result = api.api.node("delete_user", auth_tags="admin")("user123")
```

## Integration with Context (Future)

When `RoutingContext` is set, `AuthPlugin` can automatically read `avatar.tags`:

```python
# Adapter sets context
app.context = ASGIContext(request, app, server)

# avatar.tags comes from authentication middleware
# context.avatar.tags = {"admin", "hr"}

# AuthPlugin reads tags from context automatically
result = app.api.call("manage_salaries")  # checks context.avatar.tags vs auth_tags
```

## Configuration

### Per-Handler

```python
@route("api", auth_rule="admin")
def handler(self): ...
```

### Runtime Override

```python
# Disable auth for specific handler
svc.routing.configure("api:auth/handler_name", enabled=False)

# Add rule to all handlers
svc.routing.configure("api:auth/_all_", rule="internal")
```

## Exceptions

| Exception | When |
|-----------|------|
| `NotAuthorized` | `get()` or `call()` blocked by auth rule |
| `NotFound` | Entry doesn't exist |

```python
from genro_routes import NotAuthorized, NotFound

try:
    handler = api.get("delete_user", auth_tags="guest")
except NotAuthorized:
    print("Access denied")
except NotFound:
    print("Handler not found")
```

## Sentinel Value

When using `node()` with filtering, unauthorized entries return `UNAUTHORIZED` sentinel:

```python
from genro_routes import UNAUTHORIZED

info = api.node("delete_user", auth_tags="guest")
if info is UNAUTHORIZED:
    print("Not authorized to view this entry")
```

## Access Control Plugins

There are now two access control plugins with different purposes:

| Plugin | Purpose | HTTP Code | Usage |
|--------|---------|-----------|-------|
| `AuthPlugin` | User authorization | 401/403 | `auth_rule="admin"` on entry, `auth_tags="admin"` at query |
| `AllowPlugin` | System capabilities | 501 | `allow_rule="pyjwt"` on entry, `allow_capabilities="pyjwt"` at query |

**AuthPlugin** checks if the user has the required permissions.
**AllowPlugin** checks if the system has the required capabilities (e.g., optional dependencies).
