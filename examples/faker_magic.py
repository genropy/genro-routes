from __future__ import annotations

import inspect
from typing import Any

from faker import Faker

from genro_routes import RoutingClass

# -----------------------------------------------------------------------------
# MAGIC Wrapper: Automatically maps all methods of an object as routes
# -----------------------------------------------------------------------------

class MagicFakerRouter(RoutingClass):
    def __init__(self, provider_obj: Any):
        self.route.plug("pydantic")
        self._provider = provider_obj

        # Magic introspection: map all public methods of the provider
        for attr_name in dir(provider_obj):
            if attr_name.startswith("_"):
                continue

            attr = getattr(provider_obj, attr_name)
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                # Dynamically register the entry in the router
                # This is the core of genro-routes' power
                self.route.add_entry(attr, name=attr_name)

# -----------------------------------------------------------------------------
# Service exposing ALL of Faker hierarchically
# -----------------------------------------------------------------------------

class FullFakerService(RoutingClass):
    def __init__(self, locale: str = "en_US"):
        self.fake = Faker(locale=locale)

        # Map entire functionality blocks automatically
        # (Faker organizes methods internally; here we choose main providers)
        self.person = MagicFakerRouter(self.fake)
        self.address = MagicFakerRouter(self.fake)
        self.company = MagicFakerRouter(self.fake)

        self.add_branches({"name": "person", "instance": self.person})
        self.add_branches({"name": "address", "instance": self.address})
        self.add_branches({"name": "company", "instance": self.company})

if __name__ == "__main__":
    service = FullFakerService()

    print("--- FULL DYNAMIC MAPPING ACTIVE ---")

    # Now we can call ANYTHING, even if not explicitly defined!
    print(f"Name: {service.route.node('person/name')()}")
    print(f"Last Name: {service.route.node('person/last_name')()}")
    print(f"SSN: {service.route.node('person/ssn')()}")
    print(f"Company: {service.route.node('company/company')()}")
    print(f"Catch Phrase: {service.route.node('company/catch_phrase')()}")

    # And OpenAPI will reflect ALL discovered methods
    nodes = service.route.nodes()
    count = len(nodes['routers']['person']['entries'])
    print(f"\nThe 'person' router automatically exposed {count} Faker methods.")
