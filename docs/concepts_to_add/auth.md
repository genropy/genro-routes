# Auth - Authorization Plugin

**Status**: 🔴 DA REVISIONARE

## Overview

The `AuthPlugin` provides tag-based authorization for router entries. It evaluates
authorization rules defined on endpoints against user tags from the execution context.

## Terminology

| Concept | Location | Description |
|---------|----------|-------------|
| `auth_tags` | `@route(...)` | Authorization rule the endpoint requires |
| `avatar.tags` | `context.avatar` | Tags the current user has |
| `AuthPlugin` | Plugin | Evaluates rules against user tags |

## Usage

### Defining Authorization Rules

```python
from genro_routes import Router, RoutingClass, route

class AdminAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api", auth_tags="admin")
    def delete_user(self, user_id):
        """Only users with 'admin' tag can access."""
        return f"Deleted {user_id}"

    @route("api", auth_tags="admin | manager")
    def view_reports(self):
        """Users with 'admin' OR 'manager' tag can access."""
        return "Reports..."

    @route("api", auth_tags="admin & hr")
    def manage_salaries(self):
        """Users with BOTH 'admin' AND 'hr' tags can access."""
        return "Salaries..."

    @route("api")
    def public_info(self):
        """No auth_tags = public access."""
        return "Public info"
```

### Rule Syntax

| Syntax | Meaning | Example |
|--------|---------|---------|
| `"admin"` | Single tag required | User must have "admin" |
| `"admin,hr"` | OR (comma shortcut) | User must have "admin" OR "hr" |
| `"admin \| hr"` | OR (explicit) | User must have "admin" OR "hr" |
| `"admin & hr"` | AND | User must have "admin" AND "hr" |
| `"!guest"` | NOT | User must NOT have "guest" |
| `"(admin \| manager) & !suspended"` | Complex | Admin or manager, not suspended |

### Runtime Filtering

```python
api = AdminAPI()

# Filter visible entries by user tags
api.api.nodes(tags="admin")           # entries requiring 'admin'
api.api.nodes(tags="admin,manager")   # entries requiring 'admin' OR 'manager'

# Access control on get/call
handler = api.api.get("delete_user", auth_tags="admin")  # raises NotAuthorized if filtered
result = api.api.call("delete_user", auth_tags="admin", args=["user123"])
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

## Tag Inheritance

Tags inherit from parent routers using union semantics:

```python
class App(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.admin = AdminSubService()

        # All admin routes require "corporate" tag
        self.api.auth.configure(tags="corporate")
        self.api.attach_instance(self.admin, name="admin")

# AdminSubService entries now require "corporate" + their own tags
# @route("api", auth_tags="admin") becomes effectively "corporate & admin"
```

## Configuration

### Per-Handler

```python
@route("api", auth_tags="admin")
def handler(self): ...
```

### Runtime Override

```python
# Disable auth for specific handler
svc.routing.configure("api:auth/handler_name", enabled=False)

# Add tags to all handlers
svc.routing.configure("api:auth/_all_", tags="internal")
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

## Migration from FilterPlugin

The `AuthPlugin` replaces `FilterPlugin` with clearer semantics:

| Old (FilterPlugin) | New (AuthPlugin) |
|-------------------|------------------|
| `filter_tags="admin"` | `auth_tags="admin"` |
| `filter.py` | `auth.py` |
| `FilterPlugin` | `AuthPlugin` |
| `.plug("filter")` | `.plug("auth")` |

The functionality is identical - only names changed to better reflect the authorization purpose.
