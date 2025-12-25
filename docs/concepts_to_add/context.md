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

## The Solution: Abstract RoutingContext

`genro-routes` provides an abstract `RoutingContext` class. Each adapter implements
its own concrete version.

### Base Class (in genro-routes)

```python
from abc import ABC, abstractmethod

class RoutingContext(ABC):
    """Abstract execution context for routing."""

    @property
    @abstractmethod
    def db(self):
        """Database connection."""
        ...

    @property
    @abstractmethod
    def avatar(self):
        """Current user identity with metadata (permissions, locale, etc.)."""
        ...

    @property
    @abstractmethod
    def session(self):
        """Session (macro context)."""
        ...

    @property
    @abstractmethod
    def app(self):
        """Application instance."""
        ...

    @property
    @abstractmethod
    def server(self):
        """Server instance."""
        ...
```

### Concrete Implementations (in adapter packages)

```python
# genro-asgi/context.py
from genro_routes import RoutingContext

class ASGIContext(RoutingContext):
    def __init__(self, request, app, server):
        self._request = request
        self._app = app
        self._server = server

    @property
    def db(self):
        return self._request.state.db

    @property
    def avatar(self):
        return self._request.state.avatar

    @property
    def session(self):
        return self._request.state.session

    @property
    def app(self):
        return self._app

    @property
    def server(self):
        return self._server
```

```python
# genro-telegram/context.py (future)
from genro_routes import RoutingContext

class TelegramContext(RoutingContext):
    def __init__(self, message, bot, server):
        self._message = message
        self._bot = bot
        self._server = server

    @property
    def db(self):
        return self._bot.db

    @property
    def avatar(self):
        return self._message.from_user  # with telegram metadata

    @property
    def session(self):
        return self._bot.get_chat_session(self._message.chat.id)

    @property
    def app(self):
        return self._bot

    @property
    def server(self):
        return self._server
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

## Context Hierarchy

Contexts are nested (micro → macro → app → server):

```
Server (ASGI server, bot process, etc.)
└── Application (one of many apps)
    └── Session (macro context: user session, chat, etc.)
        └── Request (micro context: single request/message)
```

Access via `self.context` gives the micro context. From there you can
navigate up:

```python
self.context           # micro (current request)
self.context.session   # macro (user session)
self.context.app       # application
self.context.server    # server (if needed)
```

## Sync vs Async

| Environment | Mechanism | Reason |
|-------------|-----------|--------|
| **Sync** | Instance attribute | Single execution flow |
| **Async** | `ContextVar` | Concurrent tasks need isolation |

**Important**: Sync/async handling is the responsibility of the **concrete Context class**,
not RoutingClass. The adapter (ASGI, Telegram, etc.) provides a Context implementation
that knows how to manage its own state.

## RoutingClass Integration

RoutingClass provides a `context` property (getter/setter) for accessing the execution context.

### Implementation in RoutingClass

```python
class RoutingClass:
    __slots__ = (..., "_context")

    @property
    def context(self) -> RoutingContext | None:
        """Return the execution context, searching up the parent chain."""
        ctx = getattr(self, "_context", None)
        if ctx is not None:
            return ctx
        # Propagate from parent if not set locally
        parent = getattr(self, "_routing_parent", None)
        if parent is not None:
            return parent.context
        return None

    @context.setter
    def context(self, value: RoutingContext | None) -> None:
        """Set the execution context (must be RoutingContext or None)."""
        if value is not None and not isinstance(value, RoutingContext):
            raise TypeError("context must be a RoutingContext instance")
        object.__setattr__(self, "_context", value)
```

### Context Propagation

Context is set on the **root** RoutingClass and automatically propagates to children:

```python
# Adapter sets context on root
app.context = ASGIContext(request, db)

# Children access via parent chain
app.users.context      # → returns app.context
app.users.orders.context  # → returns app.context
```

### Adapter Usage Pattern

```python
# In genro-asgi middleware
async def dispatch(request, service):
    ctx = ASGIContext(request, app)
    service.context = ctx
    try:
        result = await service.api.call("some_method", ...)
    finally:
        service.context = None
```

## Package Structure

```text
genro-routes
└── RoutingContext (abstract base class)

genro-asgi
├── imports RoutingContext from genro-routes
└── implements ASGIContext(RoutingContext)

genro-telegram (future)
├── imports RoutingContext from genro-routes
└── implements TelegramContext(RoutingContext)

genro-cli (future)
├── imports RoutingContext from genro-routes
└── implements CLIContext(RoutingContext)
```

Each adapter package imports `RoutingContext` from `genro-routes` and provides its
own concrete implementation.

## Hypothesis: Context + Filters Integration

**Status**: Idea, not a decision

### Current State

Filters are passed explicitly:

```python
router.nodes(tags="admin")
router.get("delete_user", auth_tags=...)
```

### Possible Evolution

With Context, avatar could carry tags:

```python
context.avatar.tags = {"admin", "hr"}

@route("api", auth_rule="admin")
def delete_user(self): ...

# AuthPlugin reads context.avatar.tags automatically
```

### Open Questions

- Matching logic: subset, intersection, expression?
- Override mechanism for public entries?
- Backward compatibility with explicit filters?
