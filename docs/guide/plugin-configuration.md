# Plugin Configuration

Configure plugins at runtime through a unified API with support for global settings, per-handler overrides, and batch updates.

## Overview

Genro Routes provides `route.plug()` to attach plugins (single or in batch)
and `routing.configure()` for runtime plugin configuration with:

- **Batch attach**: Attach several plugins from a list of `{"name", ...}` dicts
- **Target syntax**: `<plugin>/<selector>` format
- **Global configuration**: Apply to all handlers with `_all_`
- **Handler-specific overrides**: Target individual handlers
- **Glob patterns**: Match multiple handlers with wildcards
- **Batch updates**: Configure multiple targets in one call
- **Introspection**: Query configuration with `"?"`

## Target Syntax

<!-- test: test_router_edge_cases.py::test_routed_configure_updates_plugins_global_and_local -->

A configuration target has two parts:

```text
<plugin_name>/<selector>
```

The router is implicit: `routing.configure()` always operates on the
instance's own router (`self.route`). Child routers belong to child
instances — configure them through the child's own `routing` proxy.

**Examples**:

- `logging/_all_` - Apply to all handlers in the logging plugin
- `logging/foo` - Apply only to the `foo` handler
- `logging/b*` - Apply to handlers matching glob pattern `b*`
- `logging` - Same as `logging/_all_` (selector defaults to `_all_`)

**Selectors**:

- `_all_` (case-insensitive) - Global plugin settings
- Handler name - Specific handler (e.g., `foo`, `bar`)
- Glob pattern - Multiple handlers (e.g., `admin_*`, `*_detail`)

## Glob Pattern Syntax

The selector part of the target supports `fnmatch` glob patterns for matching multiple handlers:

| Pattern | Matches | Example Target |
|---------|---------|----------------|
| `*` | Any string | `logging/*` (all handlers) |
| `?` | Any single character | `logging/get_?` (get_a, get_b, ...) |
| `[abc]` | Any char in brackets | `logging/get_[123]` |
| `[!abc]` | Any char NOT in brackets | `logging/[!_]*` (not starting with _) |
| `admin_*` | Prefix match | `logging/admin_*` |
| `*_detail` | Suffix match | `logging/*_detail` |

**Glob pattern examples**:

```python
class Service(RoutingClass):
    def __init__(self):
        self.route.plug("logging")

    @route()
    def admin_list(self): pass

    @route()
    def admin_create(self): pass

    @route()
    def admin_delete(self): pass

    @route()
    def user_profile(self): pass

    @route()
    def user_settings(self): pass

svc = Service()

# Disable logging for all admin handlers
svc.routing.configure("logging/admin_*", enabled=False)

# Print user handlers' log lines to stdout
svc.routing.configure("logging/user_*", print=True)

# Configure multiple patterns with comma-separated selector
svc.routing.configure("logging/admin_list,admin_create", before=False)
```

**Combining patterns**:

```python
# Multiple comma-separated patterns in selector
svc.routing.configure("logging/admin_*,user_*", enabled=True)

# Each pattern is matched independently:
# admin_* matches: admin_list, admin_create, admin_delete
# user_* matches: user_profile, user_settings
```

## Basic Configuration

<!-- test: test_router_edge_cases.py::test_routed_configure_updates_plugins_global_and_local -->

Configure plugins using keyword arguments:

```python
from genro_routes import RoutingClass, route

class ConfService(RoutingClass):
    def __init__(self):
        self.route.plug("logging")

    @route()
    def foo(self):
        return "foo"

    @route()
    def bar(self):
        return "bar"

svc = ConfService()

# Global configuration - applies to all handlers
svc.routing.configure("logging/_all_", print=True)
assert svc.route.logging.configuration()["print"] is True

# Handler-specific configuration
svc.routing.configure("logging/foo", enabled=False)
assert svc.route.logging.configuration("foo")["enabled"] is False

# Glob pattern configuration
svc.routing.configure("logging/b*", before=False)
assert svc.route.logging.configuration("bar")["before"] is False
```

**Configuration keys** depend on the plugin. Common keys:

- `enabled` - Enable/disable plugin for handler(s)
- `flags` - Boolean options as comma-separated string
- `before`, `after`, `print` - Plugin-specific settings (here: LoggingPlugin)

## Attaching Plugins in Batch

<!-- test: test_router_runtime_extras.py::test_plug_list_of_dicts_attaches_all -->

`route.plug()` attaches a plugin. Besides the single form `plug("logging")`,
it accepts a **list of plugin dicts** to attach several plugins in one call —
the natural shape for a config-driven arming layer:

```python
route.plug([
    {"name": "logging", "before": False},   # attach with options
    {"name": "pydantic"},                    # attach with defaults
])
```

**Each dictionary must have**:

- `name` key - the plugin name (validated against `Router.available_plugins()`)
- Additional keys - options passed to that plugin

Notes:

- Shared kwargs are **not** allowed with a list (`plug([...], x=1)` raises
  `ValueError`) — options live inside each dict.
- Attaching an already-attached plugin raises `ValueError` (use
  `routing.configure()` to change a live plugin's settings) — the batch form
  does not soften this.

Attaching (`plug`) and configuring (`routing.configure`) stay distinct:
`plug` brings a plugin onto the router; `configure` tunes a plugin already
attached, down to individual handlers.

## Batch Updates

<!-- test: test_router_edge_cases.py::test_routed_configure_updates_plugins_global_and_local -->

Configure multiple targets with a list of dictionaries:

```python
# JSON-friendly batch configuration
payload = [
    {"target": "logging/_all_", "flags": "print"},
    {"target": "logging/foo", "after": False},
]

result = svc.routing.configure(payload)
assert len(result) == 2
assert svc.route.logging.configuration("foo")["after"] is False
```

**Each dictionary must have**:

- `target` key - Configuration target string
- Additional keys - Configuration options

**Returns**: List of configuration results (one per target)

**Use cases**:

- External configuration files (JSON, YAML)
- HTTP API endpoints
- CLI configuration commands
- Orchestration layers

## Introspection

<!-- test: test_router_edge_cases.py::test_routed_configure_question_lists_tree -->

Query the router and plugin structure with `"?"`:

```python
class Leaf(RoutingClass):
    def __init__(self):
        self.route.plug("logging")

    @route()
    def ping(self):
        return "leaf"

class Root(RoutingClass):
    def __init__(self):
        self.route.plug("logging")
        self.leaf = Leaf()
        self.attach_instance(self.leaf, name="leaf")

    @route()
    def root_ping(self):
        return "root"

svc = Root()

# Get the router description (recursing into child routers)
info = svc.routing.configure("?")
assert info["name"] == "route"
assert info["plugins"]
assert "root_ping" in info["entries"]
assert "leaf" in info["routers"]
```

**Returns the router description dict with**:

- `name` - The router name (always `"route"`)
- `plugins` - Attached plugins with their configurations and per-handler overrides
- `entries` - Registered handler names
- `routers` - Child routers, each described with the same structure

## Exposing Configuration API

<!-- test: test_router_edge_cases.py::test_routed_configure_updates_plugins_global_and_local -->

Create a dedicated configuration endpoint:

```python
class ConfigAPI(RoutingClass):
    def __init__(self):
        self.route.plug("logging")

    @route()
    def configure_plugin(self, target: str, **options):
        """Configure plugins via API endpoint."""
        result = self.routing.configure(target, **options)
        return {"status": "ok", "result": result}

config = ConfigAPI()

# Call via router
result = config.route.node("configure_plugin")("logging/_all_", enabled=True)
assert result["status"] == "ok"
```

**Benefits**:

- External configuration without code changes
- Runtime adjustments
- API-driven configuration management
- Dynamic plugin tuning

## Error Handling

**Invalid targets raise exceptions**:

- `ValueError` - Malformed target syntax
- `AttributeError` - Plugin not found on the router
- `KeyError` - Selector matches no handlers

**Validation**:

```python
# Plugin name cannot be empty
try:
    svc.routing.configure("/_all_", enabled=True)
except ValueError:
    pass  # Expected

# Plugin must be plugged on the router
try:
    svc.routing.configure("nonexistent/_all_", enabled=True)
except AttributeError:
    pass  # Expected

# Selector must match at least one handler
try:
    svc.routing.configure("logging/nonexistent", enabled=True)
except KeyError:
    pass  # Expected
```

## Best Practices

**Global defaults, specific overrides**:

```python
# Set defaults for all handlers
svc.routing.configure("logging/_all_", enabled=True, log=True)

# Override for specific handlers
svc.routing.configure("logging/debug_*", print=True)
svc.routing.configure("logging/admin_*", enabled=False)
```

**Configuration from files**:

```python
import json

# Load from JSON configuration
with open("plugin_config.json") as f:
    config = json.load(f)

# Apply batch configuration
svc.routing.configure(config["plugins"])
```

**Gradual rollout**:

```python
# Enable new feature for test handlers only
svc.routing.configure("new_feature/test_*", enabled=True)

# Expand to all after validation
svc.routing.configure("new_feature/_all_", enabled=True)
```

## Next Steps

- **[Plugin Development](plugins.md)** - Create custom plugins
- **[Built-in Plugins](../api/plugins.md)** - LoggingPlugin and PydanticPlugin reference
- **[API Reference](../api/reference.md)** - Complete API documentation
