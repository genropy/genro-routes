# Why One Name Per Operation

## The question

> HTTP allows the same path to have different handlers for GET, POST, PUT, etc.
> Why does genro-routes enforce unique entry names instead?

## Short answer

Because genro-routes is not an HTTP router. It is a **method router** where
each entry is an **operation**, not a resource. The HTTP method is a transport
detail, resolved at the bridge layer.

## The REST model and its limits

The REST model maps four CRUD verbs to four HTTP methods on a resource path:

```
GET    /users      -> list
POST   /users      -> create
GET    /users/123  -> retrieve
PUT    /users/123  -> update
DELETE /users/123  -> delete
```

This works for simple CRUD. It breaks down as soon as operations stop being
pure CRUD:

- "Approve an invoice" is not a PUT on `/invoices/123`.
- "Send a notification" is not a POST on `/notifications`.
- "Run a report" is not a GET on `/reports`.

In practice, real APIs end up with action-based endpoints anyway:
`POST /invoices/123/approve`, `POST /reports/run`. At that point the HTTP
method is always POST and carries no semantic value - the operation name
carries all the meaning.

## Where the industry went

Modern API paradigms have moved past verb-based routing:

| Paradigm | HTTP method | Operation identity |
|----------|-------------|-------------------|
| **GraphQL** | Always POST | Query/mutation name |
| **gRPC** | Always POST (HTTP/2) | Service method name |
| **tRPC** | POST or GET | Procedure name |
| **JSON-RPC** | Always POST | `method` field |
| **MCP** (Model Context Protocol) | Always POST | Tool name |

Major REST APIs in practice also follow this pattern:

- **Stripe**: `POST /charges`, `POST /refunds` - distinct names, not
  `DELETE /charges/123`
- **GitHub**: `POST /repos/{owner}/{repo}/dispatches` - action name in path
- **OpenAI**: `POST /chat/completions` - single verb, operation is the name
- **Slack**: `POST /api/chat.postMessage` - RPC-style, method in URL

## How genro-routes handles this

In genro-routes, each handler has a unique name that **is** the operation:

```python
class OrdersAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="orders")

    @route("orders")
    def list_orders(self):
        return [...]

    @route("orders")
    def create_order(self, payload: dict):
        return {"status": "created"}

    @route("orders")
    def approve_order(self, order_id: str):
        return {"status": "approved"}
```

The HTTP method is inferred automatically when generating OpenAPI schemas:
handlers with no parameters or only scalar parameters become GET,
handlers with complex parameters become POST.

When exposed via an HTTP bridge like genro-asgi, the mapping is:

```
GET  /orders/list_orders
POST /orders/create_order
POST /orders/approve_order
```

Each operation has a clear, unambiguous name. No collision, no overloading,
no need to remember which HTTP verb maps to which behavior.

## Benefits

1. **Clarity** - `approve_order` is self-documenting. `PUT /orders/123` is not.
2. **Transport independence** - The same router works over HTTP, CLI,
   WebSocket, or MCP without changes.
3. **Introspection** - `router.nodes()` returns a flat, unambiguous map.
   No need to cross-reference paths with methods.
4. **Scalability** - APIs with hundreds of operations remain navigable.
   REST with hundreds of resources and 4 verbs each becomes a maze.
5. **Testability** - Call `router.node("approve_order")(order_id="123")`
   directly. No HTTP client needed.

## What if I need REST-style paths?

The transport bridge handles this. genro-asgi can map genro-routes entries
to REST-style paths if needed. The routing engine stays clean;
the HTTP conventions are applied at the edge.

## Summary

Genro-routes treats each handler as a named operation, not as a
verb-on-a-resource. This aligns with how modern APIs actually work and
avoids the artificial constraints of mapping everything to four HTTP verbs.
The HTTP method is a transport detail, not an architectural decision.
