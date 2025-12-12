# Genro Routes

<p align="center">
  <img src="assets/logo.png" alt="Genro Routes Logo" width="200"/>
</p>

[![PyPI version](https://img.shields.io/pypi/v/genro-routes?cacheSeconds=300)](https://pypi.org/project/genro-routes/)
[![Tests](https://github.com/genropy/genro-routes/actions/workflows/test.yml/badge.svg)](https://github.com/genropy/genro-routes/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/genropy/genro-routes/branch/main/graph/badge.svg)](https://codecov.io/gh/genropy/genro-routes)
[![Documentation](https://readthedocs.org/projects/genro-routes/badge/?version=latest)](https://genro-routes.readthedocs.io/en/latest/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Genro Routes** is a fully runtime routing engine that lets you expose Python methods as "endpoints" (CLI tools, orchestrators, internal services) without global blueprints or shared registries. Each instance creates its own routers, can attach child routers, configure plugins, and provides ready-to-use runtime introspection.

Use Genro Routes when you need to:

- Compose internal services with many handlers (application APIs, orchestrators, CLI automation)
- Build dashboards/portals that register routers dynamically and need runtime introspection
- Extend handler behavior with plugins (logging, validation, audit trails)

Genro Routes provides a consistent, well-tested foundation for these patterns.

## Key Features

1. **Instance-scoped routers** - Each object instantiates its own routers (`Router(self, ...)`) with isolated state.
2. **Friendly registration** - `@route(...)` accepts explicit names, auto-strips prefixes, and supports custom metadata.
3. **Simple hierarchies** - `attach_instance(child, name="alias")` connects RoutedClass instances with path access (`parent.api.get("child/method")`).
4. **Plugin pipeline** - `BasePlugin` provides `on_decore`/`wrap_handler` hooks and plugins inherit from parents automatically.
5. **Runtime configuration** - `routedclass.configure()` applies global or per-handler overrides with wildcards and returns reports (`"?"`).
6. **Optional extras** - `logging`, `pydantic` plugins and SmartAsync wrapping are opt-in; the core has minimal dependencies.
7. **Full coverage** - The package ships with a comprehensive test suite and no hidden compatibility layers.

## Quick Example

```python
from genro_routes import RoutedClass, Router, route

class OrdersAPI(RoutedClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="orders")

    @route("orders")
    def list(self):
        return ["order-1", "order-2"]

    @route("orders")
    def retrieve(self, ident: str):
        return f"{self.label}:{ident}"

    @route("orders")
    def create(self, payload: dict):
        return {"status": "created", **payload}

orders = OrdersAPI("acme")
print(orders.api.get("list")())        # ["order-1", "order-2"]
print(orders.api.get("retrieve")("42"))  # acme:42

overview = orders.api.members()
print(overview["entries"].keys())      # dict_keys(['list', 'retrieve', 'create'])
```

## Hierarchical Routing

Build nested service structures with path access:

```python
class UsersAPI(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list(self):
        return ["alice", "bob"]

class Application(RoutedClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.users = UsersAPI()

        # Attach child service
        self.api.attach_instance(self.users, name="users")

app = Application()
print(app.api.get("users/list")())  # ["alice", "bob"]

# Introspect hierarchy
info = app.api.members()
print(info["routers"].keys())  # dict_keys(['users'])
```

## Installation

```bash
pip install genro-routes
```

For development:

```bash
git clone https://github.com/genropy/genro-routes.git
cd genro-routes
pip install -e ".[all]"
```

To use the Pydantic plugin:

```bash
pip install genro-routes[pydantic]
```

## Core Concepts

- **`Router`** - Runtime router bound directly to an object via `Router(self, name="api")`
- **`@route("name")`** - Decorator that marks bound methods for the router with the matching name
- **`RoutedClass`** - Mixin that tracks routers per instance and exposes the `routedclass` proxy
- **`BasePlugin`** - Base class for creating plugins with `on_decore` and `wrap_handler` hooks
- **`obj.routedclass`** - Proxy exposed by every RoutedClass that provides helpers like `get_router(...)` and `configure(...)` for managing routers/plugins without polluting the instance namespace.

## Pattern Highlights

- **Explicit naming + prefixes** - `@route("api", name="detail")` and `Router(self, prefix="handle_")` separate method names from public route names.
- **Explicit instance hierarchies** - `self.api.attach_instance(self.child, name="alias")` connects RoutedClass instances with parent tracking and auto-detachment.
- **Branch routers** - `Router(self, branch=True, auto_discover=False)` creates pure organizational nodes without handlers.
- **Built-in and custom plugins** - `Router(self, ...).plug("logging")`, `Router(self, ...).plug("pydantic")`, or custom plugins.
- **Runtime configuration** - `routedclass.configure("api:logging/_all_", enabled=False)` applies targeted overrides with wildcards or batch updates.
- **Dynamic registration** - `router.add_entry(handler)` or `router.add_entry("*")` allow publishing handlers computed at runtime.

## Documentation

- **[Full Documentation](https://genro-routes.readthedocs.io/)** - Complete guides, tutorials, and API reference
- **[Quick Start](docs/quickstart.md)** - Get started in 5 minutes
- **[FAQ](docs/FAQ.md)** - Common questions and answers

## Testing

Genro Routes achieves 99% test coverage with 100 comprehensive tests:

```bash
PYTHONPATH=src pytest --cov=src/genro_routes --cov-report=term-missing
```

All examples in documentation are verified by the test suite and linked with test anchors.

## Repository Structure

```text
genro-routes/
├── src/genro_routes/
│   ├── core/               # Core router implementation
│   │   ├── router.py       # Router runtime implementation
│   │   ├── decorators.py   # @route decorator
│   │   └── routed.py       # RoutedClass mixin
│   └── plugins/            # Built-in plugins
│       ├── logging.py      # LoggingPlugin
│       └── pydantic.py     # PydanticPlugin
├── tests/                  # Test suite (99% coverage)
├── docs/                   # Documentation (Sphinx)
└── examples/              # Example implementations
```

## Project Status

Genro Routes is currently in **beta** (v0.9.0). The core API is stable with complete documentation.

- **Test Coverage**: 99% (100 tests)
- **Python Support**: 3.10, 3.11, 3.12, 3.13
- **License**: Apache 2.0

## Current Limitations

- **Instance methods only** - Routers assume decorated functions are bound methods (no static/class method or free function support)
- **No SmartAsync plugin** - `get(..., use_smartasync=True)` is optional but there's no dedicated SmartAsync plugin
- **Minimal plugin system** - Intentionally simple; advanced features must be added manually

## Roadmap

- Additional plugins (async, storage, audit trail, metrics)
- Benchmarks and performance comparison
- Example applications and use cases

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Origin

This project was originally developed as "smartroute" under MIT license and has been renamed and relicensed.
