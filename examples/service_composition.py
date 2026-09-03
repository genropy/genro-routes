# Copyright 2025-2026 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
        self.add_branches({"name": "billing", "instance": self.billing})
        self.add_branches({"name": "inventory", "instance": self.inventory})

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
