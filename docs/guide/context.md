# Execution Context

Handlers need access to shared state — database connections, the current user,
session data, application config.  But they **must not know** which adapter
(HTTP, WebSocket, bot, CLI) is calling them.

`RoutingContext` solves this: a simple container where the adapter stores
whatever the handlers need, and a `ContextVar` that makes it visible to
every `RoutingClass` in the current task.

## RoutingContext in 30 seconds

```python
from genro_routes import RoutingContext

# Create a context and attach attributes freely
ctx = RoutingContext()
ctx.db = db_connection
ctx.user = current_user
ctx.locale = "it"
```

No abstract methods, no required properties.  Just set what you need.

## Parent chain — layered contexts

Real applications have layers: a server starts, mounts an app, then handles
requests.  Each layer adds its own state without copying the parent's:

```python
# 1. Server boot — lives for the entire process
server_ctx = RoutingContext()
server_ctx.server = server
server_ctx.config = global_config

# 2. App mount — lives as long as the app is mounted
app_ctx = RoutingContext(parent=server_ctx)
app_ctx.app = app

# 3. Per-request — created and discarded for each request
request_ctx = RoutingContext(parent=app_ctx)
request_ctx.db = request.state.db
request_ctx.user = request.state.user
request_ctx.session = request.state.session
```

When a handler reads an attribute, lookup works bottom-up:

```
request_ctx.db       →  found locally         →  request.state.db
request_ctx.app      →  not local, check parent  →  app_ctx.app
request_ctx.config   →  not local, not in app_ctx, check grandparent  →  server_ctx.config
request_ctx.missing  →  not found anywhere    →  AttributeError
```

Setting an attribute locally **shadows** the parent — it does not modify it:

```python
request_ctx.config = override   # only this request sees the override
server_ctx.config               # unchanged
```

## Slot + parent chain — instance-scoped context

The context is stored in a `_ctx` slot on each `RoutingClass` instance.
Reading `self.ctx` walks up the `_routing_parent` chain until it finds a
non-None value — the same pattern used by `_routing_parent` itself.

- **Set it on the root** — children inherit it automatically via the parent chain.
- **Override locally** — a child can set its own `ctx` to shadow the parent's.
- **Clear locally** — setting `child.ctx = None` makes it fall through to the parent again.

### How it works under the hood

```python
# In routing.py (simplified)
class RoutingClass:
    __slots__ = (..., "_ctx", ...)

    @property
    def ctx(self):
        result = getattr(self, "_ctx", None)
        if result is not None:
            return result
        parent = getattr(self, "_routing_parent", None)
        if parent is not None:
            return parent.ctx
        return None

    @ctx.setter
    def ctx(self, value):
        object.__setattr__(self, "_ctx", value)
```

Concurrency isolation (ContextVar for async, threading.local for threads) is
the adapter's responsibility, not genro-routes'.

## Adapter usage pattern

An adapter (like genro-asgi) creates a per-request context and sets it on
any `RoutingClass` instance before dispatching:

```python
# In your ASGI dispatcher
async def dispatch(request, service):
    # Build a request-scoped context
    ctx = RoutingContext(parent=app_ctx)
    ctx.db = request.state.db
    ctx.user = request.state.user
    ctx.session = request.state.session

    # Set it — now every RoutingClass in this task sees it
    service.ctx = ctx
    try:
        result = await service.api.call("some_handler", ...)
    finally:
        service.ctx = None   # cleanup for this task
```

After `service.ctx = ctx`, any handler can do:

```python
@route("api")
def list_orders(self):
    db = self.ctx.db          # from request_ctx (local)
    user = self.ctx.user      # from request_ctx (local)
    config = self.ctx.config  # from server_ctx (walked up)
    return db.query(...)
```

## Database access

Before this design, a separate `DbRoutingClass` propagated `db` through the
routing hierarchy.  Now `db` lives in the context like everything else:

```python
# Old pattern (removed)
class MyServer(DbRoutingClass):
    def __init__(self, db):
        self.db = db  # stored in __slots__, propagated via _routing_parent

# New pattern
server_ctx = RoutingContext()
server_ctx.db = db_connection
svc.ctx = server_ctx

# Handler access — same as before
@route("api")
def query(self):
    return self.ctx.db.execute("SELECT 1")
```

If the adapter creates layered contexts, child contexts inherit `db` from
the parent automatically — no need to set it on every request if it's the
same connection.

## Subclassing RoutingContext

For adapters that prefer a more structured approach, subclassing works:

```python
class ASGIContext(RoutingContext):
    def __init__(self, request, app_ctx):
        super().__init__(parent=app_ctx)
        self._request = request

    @property
    def db(self):
        return self._request.state.db

    @property
    def user(self):
        return self._request.state.user
```

Properties defined on the subclass take precedence over `__getattr__` parent
delegation.  Both patterns (free attributes and subclass properties) can
coexist.

## Summary

| Concept | How it works |
|---------|-------------|
| **RoutingContext** | Simple object with free `__dict__` — attach any attribute |
| **Parent chain** | `RoutingContext(parent=...)` — missing attributes walk up |
| **Slot + parent chain** | `ctx` walks up `_routing_parent` until it finds a non-None value |
| **Setting context** | `svc.ctx = ctx` stores on the instance slot |
| **Reading context** | `self.ctx.db` reads from local slot or walks parent chain |
| **Cleanup** | `svc.ctx = None` clears local, falls through to parent |
| **Database access** | `self.ctx.db` — no more DbRoutingClass |
