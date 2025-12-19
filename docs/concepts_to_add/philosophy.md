# Philosophy - genro-routes

**Status**: 🔴 DA REVISIONARE

## The Problem

Business logic shouldn't know how it will be consumed. Whether your service
is called via HTTP, WebSocket, a Telegram bot, or a static app, the code
that does the actual work should remain the same.

Traditional frameworks like FastAPI bind routes to transport:
- Routes are strings: `"/users/123/orders"`
- You define paths explicitly
- Business logic is mixed with HTTP concerns

## The genro-routes Solution

genro-routes separates **what you expose** from **how it's consumed**.

Your business logic lives in a **tree of objects**:

```
ServiceRoot
├── alfa (instance)      → alfa/...
│   ├── xx (method)      → alfa/xx
│   ├── yy (instance)    → alfa/yy/...
│   │   └── ...
│   └── zz (method)      → alfa/zz
├── beta (instance)      → beta/...
├── gamma (method)       → gamma
└── delta (method)       → delta
```

The **path structure emerges from object composition**, not from hand-written
strings.

When you call `root.routed.get("alfa/yy/something")`, the system:
1. Finds `alfa` (instance)
2. Enters its router
3. Finds `yy` (instance)
4. Enters its router
5. Finds `something`

You navigate the tree to find published methods, and different **adapters**
can expose that same tree via any transport (HTTP, WebSocket, bot, etc.).

## Key Insight

Complex problems rarely fit in a single class. You naturally decompose them
into a hierarchy of collaborating objects. genro-routes lets you **publish
methods at any level** of that hierarchy, and the routing structure follows
the object structure automatically.
