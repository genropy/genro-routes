from __future__ import annotations

from genro_routes import RoutingClass, route


class BillingModule(RoutingClass):
    @route()
    def invoice_list(self):
        return ["Inv-001", "Inv-002"]

class InventoryModule(RoutingClass):
    @route()
    def stock_level(self, item_id: str):
        return {"item": item_id, "qty": 42}

class EnterpriseApp(RoutingClass):
    """A main application that composes multiple modules."""
    def __init__(self):
        # Instantiate separate modules
        self.billing = BillingModule()
        self.inventory = InventoryModule()

        # COMPOSITION: attach their routers to our main API
        self.attach_instance(self.billing, name="billing")
        self.attach_instance(self.inventory, name="inventory")

if __name__ == "__main__":
    app = EnterpriseApp()

    print("--- Service Composition Demo ---")

    # Accessing Billing via the main app
    print(f"Invoices: {app.route.node('billing/invoice_list')()}")

    # Accessing Inventory via the main app
    print(f"Stock: {app.route.node('inventory/stock_level')(item_id='part-123')}")

    # Introspection shows the merged structure
    nodes = app.route.nodes()
    print(f"\nMain API contains {len(nodes['routers'])} child routers: {list(nodes['routers'].keys())}")

    print("\nChild routers discovered:")
    for child_name in nodes["routers"]:
        print(f" - {child_name}")
