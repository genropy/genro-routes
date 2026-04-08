# Copyright 2025-2026 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
import inspect
from typing import Any
from faker import Faker
from genro_routes import Router, RoutingClass

# -----------------------------------------------------------------------------
# MAGIC Wrapper: Automatically maps all methods of an object as routes
# -----------------------------------------------------------------------------

class MagicFakerRouter(RoutingClass):
    def __init__(self, name: str, provider_obj: Any):
        self.router = Router(self, name=name).plug("pydantic")
        self._provider = provider_obj
        
        # Magic introspection: map all public methods of the provider
        for attr_name in dir(provider_obj):
            if attr_name.startswith("_"):
                continue
            
            attr = getattr(provider_obj, attr_name)
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                # Dynamically register the entry in the router
                # This is the core of genro-routes' power
                self.router.add_entry(attr, name=attr_name)

# -----------------------------------------------------------------------------
# Service exposing ALL of Faker hierarchically
# -----------------------------------------------------------------------------

class FullFakerService(RoutingClass):
    def __init__(self, locale: str = "en_US"):
        self.fake = Faker(locale=locale)
        self.api = Router(self, name="api")
        
        # Map entire functionality blocks automatically
        # (Faker organizes methods internally; here we choose main providers)
        self.person = MagicFakerRouter("person", self.fake)
        self.address = MagicFakerRouter("address", self.fake)
        self.company = MagicFakerRouter("company", self.fake)
        
        self.attach_instance(self.person, name="person")
        self.attach_instance(self.address, name="address")
        self.attach_instance(self.company, name="company")

if __name__ == "__main__":
    service = FullFakerService()

    print(f"--- FULL DYNAMIC MAPPING ACTIVE ---")
    
    # Now we can call ANYTHING, even if not explicitly defined!
    print(f"Name: {service.api.node('person/name')()}")
    print(f"Last Name: {service.api.node('person/last_name')()}")
    print(f"SSN: {service.api.node('person/ssn')()}")
    print(f"Company: {service.api.node('company/company')()}")
    print(f"Catch Phrase: {service.api.node('company/catch_phrase')()}")

    # And OpenAPI will reflect ALL discovered methods
    nodes = service.api.nodes()
    count = len(nodes['routers']['person']['entries'])
    print(f"\nThe 'person' router automatically exposed {count} Faker methods.")
