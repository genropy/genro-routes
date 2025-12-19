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

## The Solution: Abstract Context

`genro-routes` provides an abstract `Context` class. Each adapter implements
its own concrete version.

### Base Class (in genro-routes)

```python
from abc import ABC, abstractmethod

class Context(ABC):
    """Abstract execution context"""

    @property
    @abstractmethod
    def db(self):
        """Database connection"""
        ...

    @property
    @abstractmethod
    def user(self):
        """Current user"""
        ...

    @property
    @abstractmethod
    def session(self):
        """Session (macro context)"""
        ...

    @property
    @abstractmethod
    def app(self):
        """Application instance"""
        ...
```

### Concrete Implementations (in adapter packages)

```python
# genro-asgi/context.py
from genro_routes import Context

class ASGIContext(Context):
    def __init__(self, request, app):
        self._request = request
        self._app = app

    @property
    def db(self):
        return self._request.state.db

    @property
    def user(self):
        return self._request.user

    @property
    def session(self):
        return self._request.state.session

    @property
    def app(self):
        return self._app
```

```python
# genro-telegram/context.py (future)
from genro_routes import Context

class TelegramContext(Context):
    def __init__(self, message, bot):
        self._message = message
        self._bot = bot

    @property
    def db(self):
        return self._bot.db

    @property
    def user(self):
        return self._message.from_user

    @property
    def session(self):
        return self._bot.get_chat_session(self._message.chat.id)

    @property
    def app(self):
        return self._bot
```

## Usage in Business Logic

```python
class OrderService(RoutingClass):
    @route("api")
    def create_order(self, items):
        # Works the same with ASGI, Telegram, CLI...
        db = self.context.db
        user = self.context.user

        order = Order(user=user, items=items)
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

The adapter handles this transparently. Business code just uses `self.context`.

## Package Structure

```
genro-routes
└── Context (abstract base class)

genro-asgi
├── imports Context from genro-routes
└── implements ASGIContext(Context)

genro-telegram (future)
├── imports Context from genro-routes
└── implements TelegramContext(Context)

genro-cli (future)
├── imports Context from genro-routes
└── implements CLIContext(Context)
```

Each adapter package imports `Context` from `genro-routes` and provides its
own concrete implementation.
