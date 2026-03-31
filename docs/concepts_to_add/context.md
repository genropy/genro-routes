# Context - Execution Context Abstraction

**Status**: 🔴 DA REVISIONARE

## The Problem

During method execution, business logic may need access to:
- Database connection
- Current user
- Session data
- Application configuration
- Request details

But it **must not know** which adapter (HTTP, WebSocket, bot, CLI) is calling it.

## The Solution: Extensible RoutingContext

`genro-routes` provides `RoutingContext`, a simple extensible container with
parent chain delegation. No ABC, no abstract methods — adapters attach whatever
attributes they need.

### RoutingContext (in genro-routes)

```python
class RoutingContext:
    """Extensible execution context with parent chain delegation."""

    def __init__(self, parent=None):
        self._parent = parent

    def __getattr__(self, name):
        # Walk up _parent chain for missing attributes
        ...
```

### Usage by Adapters

```python
# Server boot
server_ctx = RoutingContext()
server_ctx.server = server

# App mount
app_ctx = RoutingContext(parent=server_ctx)
app_ctx.app = app

# Per-request (in dispatcher)
ctx = RoutingContext(parent=app_ctx)
ctx.request = request
ctx.db = request.db
ctx.session = request.session
ctx.avatar = request.user
```

Adapters can also subclass `RoutingContext` if they prefer property-based access:

```python
# genro-asgi/context.py
class ASGIContext(RoutingContext):
    def __init__(self, request, app, server_ctx):
        super().__init__(parent=server_ctx)
        self._request = request
        self._app = app

    @property
    def db(self):
        return self._request.state.db

    @property
    def app(self):
        return self._app
```

## Usage in Business Logic

```python
class OrderService(RoutingClass):
    @route("api")
    def create_order(self, items):
        # Works the same with ASGI, Telegram, CLI...
        db = self.context.db
        avatar = self.context.avatar

        order = Order(user=avatar.user_id, items=items)
        db.add(order)
        return order
```

The business logic doesn't know (and doesn't care) whether it's being called
via HTTP, a Telegram bot, or a CLI command.

## Context Hierarchy via Parent Chain

Contexts are nested via the `parent` parameter:

```
Server context (server_ctx)
└── App context (app_ctx, parent=server_ctx)
    └── Request context (ctx, parent=app_ctx)
```

Missing attribute lookups walk up the chain automatically:

```python
ctx.db       # local attribute
ctx.server   # not local → walks up to server_ctx.server
```

## ContextVar Integration

The context is stored in a `ContextVar` at module level in `routing.py`:

```python
from contextvars import ContextVar

_context_var: ContextVar[RoutingContext | None] = ContextVar(
    "routing_context", default=None
)
```

This means:

- All `RoutingClass` instances in the same task share the same context
- Each async task gets its own isolated context automatically
- Works correctly in both sync and async environments

### Adapter Usage Pattern

```python
# In genro-asgi dispatcher
async def dispatch(request, service):
    ctx = RoutingContext(parent=app_ctx)
    ctx.request = request
    ctx.db = request.state.db
    service.context = ctx
    try:
        result = await service.api.call("some_method", ...)
    finally:
        service.context = None
```

## Package Structure

```text
genro-routes
└── RoutingContext (extensible container with parent chain)

genro-asgi
├── imports RoutingContext from genro-routes
└── uses RoutingContext directly or subclasses it

genro-telegram (future)
├── imports RoutingContext from genro-routes
└── uses RoutingContext with telegram-specific attributes
```
