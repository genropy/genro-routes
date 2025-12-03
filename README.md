# Genro Routes

Instance-scoped routing engine for Python with hierarchical handlers and composable plugins.

## Installation

```bash
pip install genro-routes
```

## Quick Start

```python
from genro_routes import RoutedClass, Router, route

class Service(RoutedClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="api")

    @route("api")
    def describe(self):
        return f"service:{self.label}"

# Each instance is isolated
first = Service("alpha")
second = Service("beta")

assert first.api.get("describe")() == "service:alpha"
assert second.api.get("describe")() == "service:beta"
```

## Features

- **Instance-scoped routers** - Every object gets an isolated router with its own plugin stack
- **Hierarchical organization** - Build router trees with `attach_instance()` and dotted path traversal
- **Composable plugins** - Hook into decoration and handler execution with `BasePlugin`
- **Plugin inheritance** - Plugins propagate automatically from parent to child routers
- **Flexible registration** - Use `@route` decorator with prefixes, metadata, and explicit names
- **Runtime configuration** - Configure plugins with `routedclass.configure()` using target syntax

## Documentation

Full documentation available at [genro-routes.readthedocs.io](https://genro-routes.readthedocs.io)

## License

Apache License 2.0

## Origin

This project was originally developed as "smartroute" under MIT license and has been renamed and relicensed.
