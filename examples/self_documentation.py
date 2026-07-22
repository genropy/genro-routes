from __future__ import annotations

import inspect
from typing import Any

from genro_routes import RoutingClass

# -----------------------------------------------------------------------------
# 1. The Magic Mapper (Generalized)
# -----------------------------------------------------------------------------

class MagicRouter(RoutingClass):
    """Dynamically maps any Python object's public methods into a router."""
    def __init__(self, target: Any):
        self._target = target

        # Introspection: collect all public methods
        for attr_name in dir(target):
            if attr_name.startswith("_"):
                continue

            attr = getattr(target, attr_name)
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                # Dynamically register the entry
                self.route.add_entry(attr, name=attr_name)

# -----------------------------------------------------------------------------
# 2. Self-Documentation Service
# -----------------------------------------------------------------------------

class GenroInternalService(RoutingClass):
    """A service that exposes Genro-Routes' own internal API as a route."""
    def __init__(self):
        # META: We take our own Router instance and expose it!
        # This allows us to "remote control" or "query" the router through itself.
        self.router_ctrl = MagicRouter(self.route)

        self.add_branches({"name": "router_inspector", "instance": self.router_ctrl})

# -----------------------------------------------------------------------------
# 3. Running the Meta-Demo
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    service = GenroInternalService()

    print("--- Genro-Routes Self-Documentation Demo ---")

    # We can now call 'nodes()' on the router, THROUGH the router itself!
    # Path: router_inspector/nodes
    print("\n1. Querying the router's nodes via the API:")
    nodes_info = service.route.node("router_inspector/nodes")()
    inspector_info = nodes_info["routers"]["router_inspector"]
    print(f"Discovered entries in the inspector: {list(inspector_info['entries'].keys())}")

    # We can introspect the internal Router API through itself
    print("\n2. Inspecting the internal Router API:")
    tree = service.route.node("router_inspector/nodes")()
    print("\nAvailable internal 'Router' methods:")
    for entry_name in tree.get("entries", {}):
        print(f" - router_inspector/{entry_name}")

    print("\n--- Why this is powerful ---")
    print("This demonstrates that genro-routes can act as a management layer")
    print("for any complex system, including itself, by transforming code")
    print("into a navigable, documented endpoint.")
