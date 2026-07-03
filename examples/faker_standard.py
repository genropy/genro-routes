from __future__ import annotations
from faker import Faker
from genro_routes import RoutingClass, route

# -----------------------------------------------------------------------------
# 1. Child routers focused on specific domains
# -----------------------------------------------------------------------------

class PersonService(RoutingClass):
    def __init__(self, fake: Faker):
        self.fake = fake
        # Plug the pydantic plugin for automatic validation
        self.route.plug("pydantic")

    @route()
    def name(self) -> str:
        """Returns a full name."""
        return self.fake.name()

    @route()
    def email(self, domain: str | None = None) -> str:
        """Returns an email address, optionally for a specific domain."""
        return self.fake.email(domain=domain)

class AddressService(RoutingClass):
    def __init__(self, fake: Faker):
        self.fake = fake
        self.route.plug("pydantic")

    @route()
    def city(self) -> str:
        """Returns a city name."""
        return self.fake.city()

# -----------------------------------------------------------------------------
# 2. Main Service orchestrating the hierarchy
# -----------------------------------------------------------------------------

class FakerService(RoutingClass):
    def __init__(self, locale: str = "en_US"):
        self.fake = Faker(locale=locale)

        # Mount child services as branches of the main router
        self.person = PersonService(self.fake)
        self.address = AddressService(self.fake)
        
        # Different instances are mounted under the main router
        self.attach_instance(self.person, name="person")
        self.attach_instance(self.address, name="address")

# -----------------------------------------------------------------------------
# 3. Usage Example (Developer Experience)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    service = FakerService()

    # 1. Access via hierarchical path
    print(f"English Name: {service.route.node('person/name')()}")

    # 2. Introspection (OpenAPI)
    # genro-routes automatically generates schema for all children
    openapi = service.route.nodes(mode="openapi")
    print(f"Generated Endpoints: {list(openapi['paths'].keys())}")

    # 3. Automatic Pydantic Validation
    # If we pass a domain that is not a string, the pydantic plugin
    # intercepts the error before even calling Faker.
    try:
        service.route.node('person/email')(domain=123)
    except Exception as e:
        print(f"Validation failed as expected: {e}")
