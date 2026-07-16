# Lazy Branches — declarative subrouters, materialized on demand

**Status**: 🔴 DA REVISIONARE
**Version**: 0.1
**Last Updated**: 2026-07-15

## Summary

Introduce **branches**: subrouters declared as a factory (`cls + params`) and
**materialized only when needed**. A `RoutingClass` populates a `_branches`
dictionary of self-describing entries; each branch is **eager** (built at first
tree access) or **lazy** (built on-demand at first traversal). This lets trees
with thousands of leaves start cheaply — nothing is instantiated until walked.

This proposal also **removes** two things: the `attach_instance` API (replaced by
a single factory-based `add_branches`) and the object-identity "secondary link"
sharing mechanism (replaced by an ordinary route method that reuses another
node's callable).

## Rationale

Today a subtree is attached with `attach_instance(child_instance, name=...)`
([routing.py:169](../../src/genro_routes/core/routing.py)): the child must be
**already constructed**. On large trees this instantiates everything at boot —
expensive and usually wasteful, since most branches are never walked.

A factory (`cls + params`) can be **deferred**; a pre-built instance cannot. One
factory path is the single source of truth and is what enables lazy timing.

## Vocabulary

A branch has three views across its lifecycle — this is the mental model:

| Term | Phase | Where |
|------|-------|-------|
| **branch** | declared (factory spec) | `_branches` dict |
| **child** | materialized (real router) | `_children` dict |
| **node** | traversed | `RouterNode` from `node()` |

`branch` names the phase that today has no name: the lazy/factory declaration.
An `entry` remains a single leaf (handler method); a `branch` is a subtree.

## Model

| Axis | Decision |
|------|----------|
| Declaration | `_branches` dict **per instance**, populated by `add_branches` |
| Entry shape | self-describing **dict**: `{"name", "lazy", "cls", "params"}` |
| Add API | `add_branches(dict \| list[dict] \| generator)` — one method, singular or plural |
| Remove API | `remove_branch(name)` |
| Read | `self.branches` (inspection) |
| Params | dict, applied as `cls(**params)` at materialization |
| Eager | materialized at **first tree access** (`.route`/`nodes()`/`node()`) |
| Lazy | materialized **on-demand** at first traversal of the branch |
| `nodes()` | describes non-materialized lazy branches **without building them**, including their class-declared leaves |
| `node("@id")` | reverse lookup **only** over eager + already-materialized (skips lazy) |
| Sharing | a route method reusing another node's callable (not a framework feature) |

### Lifecycle

1. `Alfa.__init__` → `add_branches(...)` populates **only** `_branches`. No
   instance constructed.
2. First tree access → materialize **all** eager branches (idempotent guard).
   Lazy branches untouched.
3. Request for a lazy branch → materialize **that single** branch on-demand; it
   becomes a `child` in `_children`.

### Two distinct laziness levels

- **Spec enumeration** → at the `add_branches` call (a generator is consumed
  immediately, inside `__init__`). Light metadata only.
- **Instance construction** → at materialization (eager at first access, lazy
  on-demand). This is where the real saving lives.

A generator yielding only specs + lazy branches = end-to-end laziness.

### Materialization (single point, reuses existing machinery)

Construct `cls(**params)` → set `_routing_parent` → `include()` → apply plugins
(`_on_attached_to_parent` / `_propagate_plugin_to_children`,
[router.py:438](../../src/genro_routes/core/router.py), [router.py:477]) → replace
the branch with the real `child` router in `_children`. No new propagation
mechanism — moved from attach-time to materialization-time. The plugin layer
already defers work for a "declared but not yet bound" child (`child._bound`
guard, [router.py:470]).

### `nodes()` on a lazy branch

Shows: alias + `lazy` flag + the class's **declared leaves**, read from the
class-level `@route` markers **without instantiating**. Verified feasible: in
`_iter_marked_methods` ([base_router.py:417-447](../../src/genro_routes/core/base_router.py))
only `cls = type(self.instance)` (line 424) depends on the instance; the whole
scan operates on the class via `cls.__mro__` / `vars(base)` /
`_route_decorator_kw` ([decorators.py:90](../../src/genro_routes/core/decorators.py)).

### Sharing a whole branch — alias branch (symlink) — IMPLEMENTED

The old "secondary link" (same router object under two names, built on
object-identity) is replaced by an **alias branch**: a symlink to another branch,
addressed by an **absolute path** from the tree root.

```python
self.add_branches([
    {"name": "real", "cls": Leaf},
    {"name": "fake", "alias": "real"},          # symlink to the 'real' branch
])
```

- Spec: `{"name", "alias": "<absolute path>"}`; `alias` and `cls` are mutually
  exclusive (ValueError otherwise).
- Navigating into an alias **rewrites the path** to the target and resolves from
  the root: `node("fake/x")` → `real/x`. The whole subtree (branches + leaves,
  recursive) is reachable through it.
- **Plugins are the target's** — a transparent symlink; the alias adds none and
  they are not redefinable. (This is the old `include(router)` semantics, not the
  "own plugins" idea once discussed.)
- Resolution is lazy: the alias is a string; navigating it materializes lazy
  branches along the target path.
- `nodes()` shows the target's subtree under the alias name with an `alias` marker.
- Broken alias → `not_found`; alias cycle → `ValueError`. Reached from the **root**
  (absolute), not from the declaring router.

Implementation: `_find_candidate_node` / `router_at_path` / `nodes()` detect an
alias spec and rewrite via `_root_router()` + `_resolve_alias` (cycle-guarded).

### Sharing a single leaf — NOT SUPPORTED (decided)

Reusing a single leaf under a new name *with its own plugins* (own plugins +
delegated body) is **explicitly out of scope** — it will not be implemented.
Sharing is only a whole-branch alias (above). If a caller needs to expose one
handler elsewhere, they write a normal `@route` method and call the target
themselves in its body; the framework offers no dedicated leaf-alias mechanism.

## Separation of responsibility

- **framework** → provides the mechanism (`add_branches` + materialization)
- **RoutingClass author** → decides which branches are lazy (e.g. an `if lazy:`
  in the class's own `__init__`)
- **end user** → activates via an application flag (e.g. `Alfa(lazy=True)`),
  without knowing the internals. The `lazy` flag is an application convention,
  not something the framework imposes.

## Illustrative usage (not final)

```python
class Alfa(RoutingClass):
    def __init__(self, lazy=False):
        self.add_branches([
            {"name": "beta",  "lazy": lazy,  "cls": Beta,  "params": {"x": 56}},
            {"name": "gamma", "lazy": False, "cls": Gamma, "params": {}},
        ])

    # or from a discovery function the author writes however they like
    def discover(self):
        for name, cls, params in self.scan_somewhere():
            yield {"name": name, "lazy": True, "cls": cls, "params": params}
```

## Scope — files to modify (implementation phase)

| File | Change |
|------|--------|
| `core/routing.py` | `RoutingClass`: `_branches` slot, `add_branches`, `remove_branch`, `branches` property; **remove** `attach_instance`; eager-materialization guard |
| `core/base_router.py` | `_find_candidate_node` (lazy materialization on descent); `nodes()` (describe lazy branches + class leaves); `_search_endpoint_id` (skip lazy); **remove** secondary-link logic in `_include_router`; callable-reuse helper |
| `core/router.py` | materialization applies plugins (reuse existing hooks) |
| `tests/` | migrate ~89 `attach_instance` call-sites to `add_branches`; new exhaustive suite for lazy/eager, materialization, `nodes()`, `@endpoint_id`, add/remove runtime, callable reuse, deferred errors, guard idempotency |
| `docs/` | update guides referencing `attach_instance` (e.g. `guide/attach-instance-visual-guide.md`) |

## Open questions

- Exact API for the callable-reuse helper (argument / `ctx` forwarding semantics).
- Slot count on `RoutingClass` `__slots__` ([routing.py:116]): new slot(s) for
  `_branches` and the eager-materialization idempotent guard.

## Out of scope

- This document is a **proposal**, not source of truth, until approved.
- Implementation follows tests-first, one block at a time, suite green at each step.
