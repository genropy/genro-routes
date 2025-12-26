# Examples Gallery

Learning by example is often the fastest way to understand the architectural power of `genro-routes`. This gallery showcases a variety of use cases, from simple library wrappers to complex service compositions.

```{tip}
**New to Genro-Routes?** Read our architectural deep-dive: [Why wrap a library with Genro-Routes?](https://github.com/genropy/genro-routes/blob/main/examples/WHY_GENRO_ROUTES.md)
```

## Library Wrappers

These examples show how to take existing Python libraries and turn them into robust, validated, and self-documenting services.

### 1. Standard Faker
Demonstrates explicit routing using the `{route}` decorator. Perfect for well-defined APIs where you want full control over which methods are exposed.
- **Source**: [examples/faker_standard.py](https://github.com/genropy/genro-routes/blob/main/examples/faker_standard.py)

### 2. Magic Faker (Dynamic Mapping)
Shows how to use Python introspection to automatically map **all public methods** of a library (Faker providers) into the routing tree with zero boilerplate.
- **Source**: [examples/faker_magic.py](https://github.com/genropy/genro-routes/blob/main/examples/faker_magic.py)

### 3. Syntax Highlighting (Pygments)
Turns the **Pygments** library into a service. It demonstrates how Pydantic validation protects complex formatting options (HTML vs ANSI).
- **Source**: [examples/pygments_highlighting.py](https://github.com/genropy/genro-routes/blob/main/examples/pygments_highlighting.py)

### 4. QR Code Generator
A classic "Asset Generation as a Service" example. Shows how to validate input data before triggering expensive image processing.
- **Source**: [examples/qrcode_generator.py](https://github.com/genropy/genro-routes/blob/main/examples/qrcode_generator.py)

## Architectural Patterns

### 5. Authentication & Roles
A deep dive into the `AuthPlugin`. Shows how to protect specific nodes with role tags and how to handle the new specific exceptions like `NotAuthenticated` and `NotAuthorized`.
- **Source**: [examples/auth_roles.py](https://github.com/genropy/genro-routes/blob/main/examples/auth_roles.py)

### 6. Service Composition
One of the most powerful features of the library. Shows how to build a large application by mounting independent `RoutingClass` modules (like "Billing" and "Inventory") into a single, unified hierarchical tree.
- **Source**: [examples/service_composition.py](https://github.com/genropy/genro-routes/blob/main/examples/service_composition.py)

### 7. Self-Documentation (Meta-Example)
The ultimate demonstration of dynamic mapping: **genro-routes documenting itself**. Exposes the internal `Router` API as a service, showing how to use the library as a transparent management layer for existing codebases.
- **Source**: [examples/self_documentation.py](https://github.com/genropy/genro-routes/blob/main/examples/self_documentation.py)

---

## Running the Examples

You can find all these files in the `examples/` directory of the repository. To run them:

1. Clone the repository.
2. Install dependencies: `pip install faker pygments qrcode[pil]`.
3. Run any example directly: `python examples/faker_standard.py`.
