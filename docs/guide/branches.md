# Branches: Lazy Subtrees and Aliases

Declare subtrees as factory specs and build them only when needed. On trees
with thousands of leaves, branches let the application start instantly:
nothing is constructed until a path is actually traversed.

## Overview

A **branch** is a child subtree declared as a self-describing spec instead of
an already-built instance. The same object has three views across its
lifecycle:

| Term | Phase | Where |
|------|-------|-------|
| **branch** | declared (factory spec) | the router's declared branches |
| **child** | materialized (real router) | the router's children |
| **node** | traversed | `RouterNode` from `node()` |

The mental model is a file explorer: declaring a branch puts a closed folder
in the tree; opening it (traversing a path through it) builds its content;
sub-folders stay closed until you open them too.

## Declaring Branches

`add_branches` accepts one spec dict, a list, or any iterable/generator:

```python
from genro_routes import RoutingClass, route

class UsersAPI(RoutingClass):
    @route()
    def list(self):
        return ["alice", "bob"]

class SalesAPI(RoutingClass):
    def __init__(self, region: str = "eu"):
        self.region = region

    @route()
    def report(self):
        return f"sales:{self.region}"

class Application(RoutingClass):
    def __init__(self):
        self.add_branches([
            {"name": "users", "cls": UsersAPI},                              # eager
            {"name": "sales", "cls": SalesAPI, "params": {"region": "us"},
             "lazy": True},                                                  # lazy
        ])

app = Application()
assert app.route.node("sales/report")() == "sales:us"
```

A **factory spec** has these fields:

| Field | Required | Meaning |
|-------|----------|---------|
| `name` | yes | alias under which the child is reachable (path segment) |
| `cls` | yes | the `RoutingClass` subclass to instantiate |
| `params` | no (default `{}`) | kwargs applied as `cls(**params)` at materialization |
| `lazy` | no (default `False`) | when the instance is built (see below) |

Declaring **never constructs anything** — specs are stored, instances come
later. A generator can therefore yield thousands of specs at zero cost:

```python
class Application(RoutingClass):
    def __init__(self):
        self.add_branches(self.discover())

    def discover(self):
        for name, cls, params in self.scan_catalog():
            yield {"name": name, "lazy": True, "cls": cls, "params": params}
```

Note the **two distinct laziness levels**: spec *enumeration* happens at the
`add_branches` call (the generator is consumed immediately — light metadata
only); instance *construction* happens at materialization. The real saving on
large trees is the second one.

## Eager vs Lazy

- **Eager** (`lazy: False`, the default): materialized at the **first tree
  access** (`nodes()`, `node()`, …). Equivalent in effect to attaching the
  instance up front, but deferred to when the tree is first touched.
- **Lazy** (`lazy: True`): materialized **on demand**, the first time a path
  traverses that segment. Once built, the branch is a normal child — the
  folder stays open.

```python
class Application(RoutingClass):
    def __init__(self):
        self.add_branches({"name": "sales", "cls": SalesAPI, "lazy": True})

app = Application()
app.route.nodes()                  # sales NOT built (introspection never builds)
app.route.node("sales/report")()   # first traversal: SalesAPI() is built HERE
```

**Materialization** is the single point where an instance is born: the
framework constructs `cls(**params)`, wires the parent chain
(`_routing_parent`), links the child router, and applies **plugin
inheritance** — exactly as an explicit `attach_instance` would have done.
Plugins plugged on the parent *after* the declaration reach the branch too,
at materialization time.

## Aliases: Symlinks to Branches

An **alias branch** exposes an existing subtree under a second name — a
transparent symlink, addressed by **absolute path from the tree root**:

```python
class Application(RoutingClass):
    def __init__(self):
        self.add_branches([
            {"name": "sales", "cls": SalesAPI},
            {"name": "shop", "alias": "sales"},        # symlink to the sales branch
        ])

app = Application()
assert app.route.node("shop/report")() == app.route.node("sales/report")()
```

- The spec has `alias` and **no** `cls`/`params` (mutually exclusive —
  `ValueError` otherwise).
- Navigating into the alias **rewrites the path**: `shop/report` resolves
  `sales/report` from the root. The whole target subtree (branches and
  leaves, recursively) is reachable through it.
- **Plugins are the target's.** The alias adds none and cannot redefine them
  — it is a link, not a wrapper.
- The alias target may be (or cross) a lazy branch: navigating the alias
  materializes whatever the target path needs.
- A **broken alias** (target does not resolve) yields `not_found`, like a
  dangling symlink. An **alias cycle** (`a → b → a`) raises `ValueError`.
- **Realpath semantics**: a node resolved through an alias reports the
  *target's* path — `app.route.node("shop/report").path == "sales/report"`.
  This is the path used by `get_url` and error messages.

## Introspection: nodes() Never Builds

`nodes()` describes declared branches **without constructing them**:

- a **lazy branch** appears with its name, a `lazy: True` flag, and the
  `@route` leaves *declared by its class* — read from the class itself, no
  instance involved;
- an **alias** appears as an unresolved marker: `{"name": ..., "alias": target}`.

To expand, you opt in explicitly:

```python
app.route.nodes()                    # markers only, zero construction
app.route.nodes(basepath="sales")    # open ONE branch (materializes it)
app.route.nodes(_eager=True)         # open EVERYTHING: materialize all lazy
                                     # branches, resolve all aliases (e.g. to
                                     # generate a full OpenAPI document)
```

`nodes(_eager=True)` raises `ValueError` if an alias cycle exists anywhere in
the expansion.

## Reverse Lookup and Lazy Branches

`node("@endpoint_id")` searches eager and already-materialized branches only:
it **skips** lazy branches that were never opened (searching them would force
the whole tree to build, defeating laziness). An endpoint inside a lazy
branch becomes findable after the branch materializes.

## Errors Are Deferred and Repeatable

A constructor that raises does so **when the branch is built**, not at
declaration:

- **lazy** branch: the error surfaces at the first traversal — and at every
  retry, until the branch is fixed or removed. The spec is never lost.
- **eager** branch: the error surfaces at the first tree access and repeats
  on every access — the tree is loudly broken until the branch is fixed or
  removed with `remove_branch`.

## Runtime Management

```python
app.add_branches({"name": "extra", "cls": ExtraAPI, "lazy": True})  # add at runtime
app.remove_branch("extra")     # drop a declared branch; if already
                               # materialized, its child is detached
app.branches                   # dict of DECLARED specs — a branch leaves this
                               # view once materialized (it is a child then)
```

Note the `branches` property semantics: it lists what is *declared and not
yet built*. After materialization the branch appears among the router's
children (e.g. in `nodes()`), not in `branches`.

## Relation to attach_instance

`attach_instance(child, name=...)` (attaching an already-built instance)
remains fully supported. `add_branches` is the **recommended declarative
form**: it enables lazy construction, keeps `__init__` free of instantiation
order concerns, and scales to generated trees. Both wire the same parent
chain and plugin inheritance.

## Next Steps

- **[Hierarchies Guide](hierarchies.md)** - Instance attachment and navigation
- **[Plugin Configuration](plugin-configuration.md)** - Configure plugins across hierarchies
- **[API Reference](../api/reference.md)** - Complete API documentation
