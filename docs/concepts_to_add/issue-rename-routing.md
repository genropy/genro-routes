# Issue: Rename RoutingClass → RoutingClass and routing → routing

**Status**: 🔴 DA REVISIONARE

## Summary

Rename the main class and property for better semantics:
- `RoutingClass` → `RoutingClass`
- `self.routing` → `self.routing`

## Rationale

- `RoutingClass` describes what the class **does** (manages routing), not what it **is**
- `self.routing` is clearer: "access the routing system"
- Consistency: `RoutingClass` → `self.routing`

## Scope

### Files to modify

#### Source (src/genro_routes/)

| File | Changes |
|------|---------|
| `__init__.py` | Export name, docstring |
| `core/__init__.py` | Import/export |
| `core/routed.py` | **Main change**: class definition, property, type hints |
| `core/decorators.py` | Re-export, docstrings |
| `core/base_router.py` | String check `"RoutingClass"`, docstrings, errors |
| `core/router.py` | Docstrings |
| `plugins/pydantic.py` | Docstrings |
| `plugins/openapi.py` | Docstrings |
| `plugins/logging.py` | Docstrings |

#### Tests (tests/)

| File | Occurrences |
|------|-------------|
| `test_router_basic.py` | ~99 |
| `test_coverage_gaps.py` | ~44 |
| `test_router_runtime_extras.py` | ~83 + 26 (property) |
| `test_router_edge_cases.py` | ~54 + 7 (property) |
| `test_filter_plugin.py` | ~44 |
| `test_router_filters_and_validation.py` | ~1 |
| `test_plugins_new.py` | ~8 |
| `test_pydantic_plugin.py` | ~3 |

#### Documentation (docs/)

| File | Occurrences |
|------|-------------|
| `index.md` | ~2 |
| `quickstart.md` | ~6 |
| `installation.md` | ~1 |
| `FAQ.md` | ~9 + 9 (property) |
| `ARCHITECTURE.md` | ~3 |
| `guide/basic-usage.md` | ~28 |
| `guide/hierarchies.md` | ~48 + 2 (property) |
| `guide/plugins.md` | ~11 + 1 (property) |
| `guide/best-practices.md` | ~19 + 6 (property) |
| `guide/plugin-configuration.md` | ~11 + 20 (property) |
| `README.md` (root) | ~11 + 3 (property) |
| `CLAUDE.md` | ~1 |

#### Also rename

- File `src/genro_routes/core/routed.py` → `src/genro_routes/core/routing.py`

## Execution Plan

### Phase 1: Core rename (source code)

1. Rename file `routed.py` → `routing.py`
2. In `routing.py`:
   - `class RoutingClass:` → `class RoutingClass:`
   - `def routing(self)` → `def routing(self)`
   - Update all type hints and docstrings
3. Update imports in `core/__init__.py`
4. Update imports in `__init__.py`
5. Update string check in `base_router.py`
6. Update docstrings in all plugins

### Phase 2: Tests

7. Global replace in all test files:
   - `RoutingClass` → `RoutingClass`
   - `.routing.` → `.routing.`

### Phase 3: Documentation

8. Global replace in all docs:
   - `RoutingClass` → `RoutingClass`
   - `.routing` → `.routing`
   - `routing` → `routing` (in prose)

### Phase 4: Verify

9. Run all tests: `pytest`
10. Build docs: `mkdocs build`
11. Verify no old references remain: `grep -r "RoutingClass\|routing" .`

## Estimated effort

- ~940 replacements total
- Mostly mechanical (find/replace)
- Risk: low (Alpha stage, no external users)

## Notes

- No deprecation warnings needed (Alpha stage)
- No backwards compatibility shims
- Clean break
