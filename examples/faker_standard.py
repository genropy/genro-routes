from __future__ import annotations
from typing import Any
from faker import Faker
from genro_routes import Router, RoutingClass, route

# -----------------------------------------------------------------------------
# 1. Child routers focused on specific domains
# -----------------------------------------------------------------------------

class PersonService(RoutingClass):
    def __init__(self, fake: Faker):
        self.fake = fake
        # Plug the pydantic plugin for automatic validation
        self.router = Router(self, name="person").plug("pydantic")

    @route("person")
    def name(self) -> str:
        """Returns a full name."""
        return self.fake.name()

    @route("person")
    def email(self, domain: str | None = None) -> str:
        """Returns an email address, optionally for a specific domain."""
        return self.fake.email(domain=domain)

class AddressService(RoutingClass):
    def __init__(self, fake: Faker):
        self.fake = fake
        self.router = Router(self, name="address").plug("pydantic")

    @route("address")
    def city(self) -> str:
        """Returns a city name."""
        return self.fake.city()

# -----------------------------------------------------------------------------
# 2. Main Service orchestrating the hierarchy
# -----------------------------------------------------------------------------

class FakerService(RoutingClass):
    def __init__(self, locale: str = "en_US"):
        self.fake = Faker(locale=locale)
        
        # Main router
        self.api = Router(self, name="api")
        
        # Mount child services as branches of the main router
        self.person = PersonService(self.fake)
        self.address = AddressService(self.fake)
        
        # Different instances are mounted under the same logical router
        self.api.attach_instance(self.person)
        self.api.attach_instance(self.address)

# -----------------------------------------------------------------------------
# 3. Usage Example (Developer Experience)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    service = FakerService()

    # 1. Access via hierarchical path
    print(f"English Name: {service.api.node('person/name')()}")

    # 2. Introspection (OpenAPI)
    # genro-routes automatically generates schema for all children
    openapi = service.api.nodes(mode="openapi")
    print(f"Generated Endpoints: {list(openapi['paths'].keys())}")

    # 3. Automatic Pydantic Validation
    # If we pass a domain that is not a string, the pydantic plugin
    # intercepts the error before even calling Faker.
    try:
        service.api.node('person/email')(domain=123)
    except Exception as e:
        print(f"Validation failed as expected: {e}")
