# Issue: Add abstract Context class

**Status**: 🔴 DA REVISIONARE

## Summary

Add an abstract `Context` class to genro-routes that defines the execution context interface. Adapter packages (genro-asgi, genro-telegram, etc.) will implement concrete versions.

## Rationale

During method execution, business logic may need access to:
- Database connection
- Current user
- Session data
- Application instance

But it **must not know** which adapter is calling it. The abstract `Context` provides a uniform interface.

## Design

### Context hierarchy

```
Server (ASGI server, bot process, etc.)
└── Application (one of many apps)
    └── Session (macro context: user session, chat)
        └── Request (micro context: single request/message)
```

### Abstract class

```python
# src/genro_routes/context.py

from abc import ABC, abstractmethod
from typing import Any, Optional

class Context(ABC):
    """Abstract execution context.

    Adapter packages implement concrete versions:
    - genro-asgi: ASGIContext
    - genro-telegram: TelegramContext
    - etc.
    """

    @property
    @abstractmethod
    def db(self) -> Any:
        """Database connection/session."""
        ...

    @property
    @abstractmethod
    def user(self) -> Any:
        """Current user."""
        ...

    @property
    @abstractmethod
    def session(self) -> Any:
        """Session (macro context)."""
        ...

    @property
    @abstractmethod
    def app(self) -> Any:
        """Application instance."""
        ...

    @property
    def server(self) -> Optional[Any]:
        """Server instance (optional)."""
        return None

    @property
    def parent(self) -> Optional['Context']:
        """Parent context for navigation."""
        return None
```

### Access from RoutingClass

```python
class OrderService(RoutingClass):
    @route("api")
    def create_order(self, items):
        db = self.context.db
        user = self.context.user
        # ...
```

### Sync vs Async

| Environment | Mechanism | Implementation |
|-------------|-----------|----------------|
| Sync | Instance attribute `_context` | Set by adapter before call |
| Async | `ContextVar` | Set by adapter, isolated per task |

The `self.context` property handles this transparently.

## Execution Plan

### Phase 1: Create Context class

1. Create `src/genro_routes/context.py`
2. Define abstract `Context` class
3. Export from `__init__.py`

### Phase 2: Integrate with RoutingClass

4. Add `_context` slot to RoutingClass
5. Add `context` property that returns current context
6. Add `ContextVar` for async support

### Phase 3: Tests

7. Create `tests/test_context.py`
8. Test abstract class behavior
9. Test sync/async context access

### Phase 4: Documentation

10. Update `docs/concepts_to_add/context.md` → move to `docs/guide/`
11. Add examples to quickstart

## Dependencies

- Requires issue "Rename RoutingClass → RoutingClass" to be completed first
- No external dependencies

## Future work (not in this issue)

- `ASGIContext` implementation in genro-asgi
- `TelegramContext` implementation in genro-telegram
- Context middleware/decorators

## Notes

- Keep the abstract class minimal
- Adapters can extend with additional properties
- `db`, `user`, `session`, `app` are the core required properties
