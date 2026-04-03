# attach_instance Visual Guide

How to connect RoutingClass instances into hierarchies.

## Core Concept

`attach_instance` lives on **RoutingClass** (not on Router). It does two things:

1. Sets the parent-child relationship (`child._routing_parent = self`)
2. Links child routers into parent routers (`parent_router._children[alias] = child_router`)

```mermaid
graph LR
    subgraph "RoutingClass (parent)"
        P["self"]
        PR["api (Router)"]
        P --> PR
    end
    subgraph "RoutingClass (child)"
        C["child"]
        CR["api (Router)"]
        C --> CR
    end
    P -- "_routing_parent" --> C
    PR -- "_children['sales']" --> CR
    style P fill:#e1f5fe
    style C fill:#fff3e0
```

---

## Scenario 1: One-to-One

Parent has **1 router**, child has **1 router**.

```mermaid
graph TB
    subgraph "Parent"
        PA["api (Router)"]
        PA --- E1["health &bull; entry"]
        PA --- E2["status &bull; entry"]
        PA === S1["[sales]"]
    end
    subgraph "Child (vendite)"
        CA["api (Router)"]
        CA --- E3["ordini &bull; entry"]
        CA --- E4["fatture &bull; entry"]
    end
    S1 --> CA

    style PA fill:#bbdefb
    style CA fill:#ffe0b2
    style S1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

**Syntax:**

```python
self.attach_instance(vendite, name="sales")
```

**Access paths:**

```python
self.api.node("health")()         # local entry
self.api.node("sales/ordini")()   # child entry
self.api.node("sales/fatture")()  # child entry
```

**Rule:** `name=` shortcut works only when child has exactly one router.

---

## Scenario 2: One parent router, two child routers — child "dissolves"

Child's routers are flattened into the parent's single router. The child instance does not appear as an intermediate node.

```mermaid
graph TB
    subgraph "Parent"
        PA["api (Router)"]
        PA --- E1["health &bull; entry"]
        PA === S1["[sales]"]
        PA === S2["[tech]"]
    end
    subgraph "Child (vendite)"
        CA["orders (Router)"]
        CA --- E3["ordini &bull; entry"]
        CB["support (Router)"]
        CB --- E4["ticket &bull; entry"]
    end
    S1 --> CA
    S2 --> CB

    style PA fill:#bbdefb
    style CA fill:#ffe0b2
    style CB fill:#ffe0b2
    style S1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style S2 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

**Syntax:**

```python
self.attach_instance(vendite, router_api="orders:sales,support:tech")
```

**Format:** `router_<parent_router>="<child_router>:<alias>,<child_router>:<alias>"`

**Access paths:**

```python
self.api.node("sales/ordini")()   # from child.orders
self.api.node("tech/ticket")()    # from child.support
```

---

## Scenario 3: One parent router, two child routers — child "appears" with one router

Only one of the child's routers is linked. The child appears as a node in the hierarchy, and any sub-routers of the linked router come along.

```mermaid
graph TB
    subgraph "Parent"
        PA["api (Router)"]
        PA --- E1["health &bull; entry"]
        PA === S1["[sales]"]
    end
    subgraph "Child (vendite)"
        CA["api (Router)"]
        CA --- E3["ordini &bull; entry"]
        CA --- E4["fatture &bull; entry"]
        CA === SS["[statistiche]"]
        CB["admin (Router)"]
        CB --- E5["gestione &bull; entry"]
    end
    subgraph "Grandchild"
        GR["stats (Router)"]
        GR --- E6["mensili &bull; entry"]
        GR --- E7["annuali &bull; entry"]
    end
    S1 --> CA
    SS --> GR

    style PA fill:#bbdefb
    style CA fill:#ffe0b2
    style CB fill:#ffe0b2,stroke-dasharray: 5 5
    style S1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style SS fill:#c8e6c9
    style GR fill:#f3e5f5
```

**Syntax:**

```python
self.attach_instance(vendite, router_api="api:sales")
# Only vendite.api is linked. vendite.admin is NOT attached.
```

**Access paths:**

```python
self.api.node("sales/ordini")()              # child entry
self.api.node("sales/statistiche/mensili")() # grandchild entry
# self.api.node("???/gestione")  -- NOT accessible (admin not linked)
```

---

## Scenario 4: Two parent routers, one child router — parent chooses where

```mermaid
graph TB
    subgraph "Parent"
        PA["api (Router)"]
        PA --- E1["health &bull; entry"]
        PA === S1["[users]"]
        PB["admin (Router)"]
        PB --- E2["dashboard &bull; entry"]
    end
    subgraph "Child"
        CA["api (Router)"]
        CA --- E3["list &bull; entry"]
        CA --- E4["detail &bull; entry"]
    end
    S1 --> CA

    style PA fill:#bbdefb
    style PB fill:#bbdefb
    style CA fill:#ffe0b2
    style S1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

**Syntax:**

```python
self.attach_instance(child, router_api="api:users")
```

The kwarg `router_api` targets the parent's `api` router. The child could be linked to `admin` instead:

```python
self.attach_instance(child, router_admin="api:users")
```

**Note:** `name=` does NOT work here because the parent has multiple routers.

---

## Scenario 5: Two parent routers, two child routers — cross-mapping

```mermaid
graph TB
    subgraph "Parent"
        PA["api (Router)"]
        PA --- E1["health &bull; entry"]
        PA === S1["[sales]"]
        PB["admin (Router)"]
        PB --- E2["dashboard &bull; entry"]
        PB === S2["[management]"]
    end
    subgraph "Child (vendite)"
        CA["orders (Router)"]
        CA --- E3["ordini &bull; entry"]
        CB["mgmt (Router)"]
        CB --- E4["gestione &bull; entry"]
    end
    S1 --> CA
    S2 --> CB

    style PA fill:#bbdefb
    style PB fill:#bbdefb
    style CA fill:#ffe0b2
    style CB fill:#ffe0b2
    style S1 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style S2 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

**Syntax:**

```python
self.attach_instance(vendite,
    router_api="orders:sales",
    router_admin="mgmt:management",
)
```

Each `router_<parent_router>` kwarg specifies which child routers go into which parent router.

**Access paths:**

```python
self.api.node("sales/ordini")()           # parent.api -> child.orders
self.admin.node("management/gestione")()  # parent.admin -> child.mgmt
```

---

## Syntax Reference

### `name=` shortcut (1:1)

```python
self.attach_instance(child, name="alias")
```

- Child must have **exactly one** router
- Parent must have **exactly one** router
- The child's single router is linked under `alias` in the parent's single router

### `router_*` kwargs (any mapping)

```python
self.attach_instance(child,
    router_<parent_router>="<child_router>:<alias>,<child_router>:<alias>",
    router_<parent_router>="<child_router>:<alias>",
)
```

- Works with any number of parent/child routers
- Multiple child routers can be linked to the same parent router (comma-separated)
- Different child routers can go to different parent routers (separate kwargs)

### Attach only (no routing)

```python
self.attach_instance(child)
```

- Sets `child._routing_parent = self` only
- No routers are linked
- Useful when you plan to link routers later or only need the parent chain for `ctx` propagation

### `detach_instance` (on Router)

```python
self.api.detach_instance(child)
```

- Removes all of `child`'s routers from this router's `_children`
- Clears `child._routing_parent`
- Stays on **Router**, not RoutingClass

---

## Decision Guide

```mermaid
flowchart TD
    A["How many routers does the child have?"] --> B{"1 router"}
    A --> C{"2+ routers"}

    B --> D{"Parent has 1 router?"}
    D -->|Yes| E["name='alias'"]
    D -->|No| F["router_X='child_router:alias'"]

    C --> G{"All go to same parent router?"}
    G -->|Yes| H["router_X='a:alias1,b:alias2'"]
    G -->|No| I["router_X='a:alias1'\nrouter_Y='b:alias2'"]

    style E fill:#c8e6c9,stroke:#2e7d32
    style F fill:#fff3e0,stroke:#ef6c00
    style H fill:#fff3e0,stroke:#ef6c00
    style I fill:#fff3e0,stroke:#ef6c00
```

---

## Real-World Example

```python
from genro_routes import RoutingClass, Router, route

class AuthService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def login(self, username: str, password: str):
        return {"token": "..."}

class UserService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list_users(self):
        return ["alice", "bob"]

class Application(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("logging")
        self.auth = AuthService()
        self.users = UserService()

        self.attach_instance(self.auth, name="auth")
        self.attach_instance(self.users, name="users")

app = Application()

app.api.node("auth/login")("alice", "secret")
app.api.node("users/list_users")()
```
