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

### Sharing — callable reuse, not object sharing

The old "secondary link" (same router object under two names, built on
object-identity `is` / `_routing_parent` primary-vs-secondary in
`_include_router` [base_router.py:571-585]) is **removed** — incompatible with
factory-only.

Sharing becomes an ordinary route method that takes another node's **callable**
and registers it as its own:

```python
class Alfa(RoutingClass):
    @route()          # 'sales' is a normal entry, with ITS OWN plugins
    def sales(self, ...):
        ...           # its callable is child's, taken via get_node("child")
```

- **Common factor = only the callable.** Plugins are NOT shared: `sales` runs its
  own plugins, then executes child's method.
- The reused callable is a **bound method** ([base_router.py:407]) — stays bound
  to child's instance (operates on child's data); only the plugin context is
  sales's.
- Reusing the callable of a **lazy** branch **forces its materialization** at that
  moment. Accepted.

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
