# Copyright 2025 Softwell S.r.l.
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

"""Additional coverage tests for runtime-only Router behavior."""

import sys
import pytest

from genro_routes import RoutingClass, Router, route
from genro_routes.core.routing import is_routing_class
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class ManualService(RoutingClass):
    """Service with manual router registration."""

    def __init__(self):
        self.api = Router(self, name="api")

    def first(self):
        return "first"

    def second(self):
        return "second"

    @route("api", marker="yes")
    def auto(self):
        return "auto"


class DualRoutes(RoutingClass):
    def __init__(self):
        self.one = Router(self, name="one")
        self.two = Router(self, name="two")

    @route("one")
    @route("two", name="two_alias")
    def shared(self):
        return "shared"


class MultiChild(RoutingClass):
    def __init__(self):
        self.router_a = Router(self, name="router_a")
        self.router_b = Router(self, name="router_b")


class SlotRouted(RoutingClass):
    __slots__ = ("slot_router",)

    def __init__(self):
        self.slot_router = Router(self, name="slot")


class DuplicateMarkers(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def original(self):
        return "ok"

    alias = original


class StampPlugin(BasePlugin):
    plugin_code = "stamp_extra"
    plugin_description = "Stamps entries for testing"

    def on_decore(self, router, func, entry: MethodEntry):
        entry.metadata["stamped"] = True


if "stamp_extra" not in Router.available_plugins():
    Router.register_plugin(StampPlugin)


class LoggingService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("logging")

    @route("api")
    def hello(self):
        return "ok"


def test_router_requires_owner():
    with pytest.raises(ValueError):
        Router(None)  # type: ignore[arg-type]


def test_register_plugin_requires_plugin_code():
    class DummyPlugin(BasePlugin):
        pass  # Missing plugin_code

    with pytest.raises(ValueError, match="missing plugin_code"):
        Router.register_plugin(DummyPlugin)


def test_plug_validates_type_and_known_plugin():
    svc = ManualService()
    with pytest.raises(TypeError):
        svc.api.plug(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.api.plug("missing_plugin")


def test_plug_rejects_duplicate_plugin():
    """Plugging the same plugin twice should raise ValueError."""
    svc = ManualService()
    svc.api.plug("logging")
    with pytest.raises(ValueError, match="already attached"):
        svc.api.plug("logging")


def test_add_entry_variants_and_wildcards():
    svc = ManualService()
    svc.api.add_entry(["first", "second"])
    assert "first" in svc.api._entries
    assert "second" in svc.api._entries

    svc.api.add_entry("first, second", replace=True)
    before = set(svc.api._entries.keys())
    assert svc.api.add_entry("   ") is svc.api
    assert set(svc.api._entries.keys()) == before

    with pytest.raises(TypeError):
        svc.api.add_entry(123)

    # Use replace=True since "auto" was already registered by lazy binding
    svc.api.add_entry("*", metadata={"source": "wild"}, replace=True)
    entry = svc.api._entries["auto"]
    assert entry.metadata["marker"] == "yes"
    assert entry.metadata["source"] == "wild"


def test_plugin_on_decore_runs_for_existing_entries():
    svc = ManualService()
    svc.api.plug("stamp_extra")
    svc.api.add_entry(svc.first, name="alias_first")
    assert svc.api._entries["alias_first"].metadata["stamped"] is True


def test_iter_marked_methods_deduplicate_same_function():
    """Test that duplicate markers on same function don't cause double registration."""
    svc = DuplicateMarkers()
    assert svc.api.node("original")() == "ok"
    # Verify only one entry via nodes()
    info = svc.api.nodes()
    assert len(info.get("entries", {})) == 1


def test_mro_override_derived_wins():
    """Test that derived class method overrides base class method (issue #11).

    When a subclass overrides a method decorated with @route, the Router should
    respect Python's MRO and use the overridden method instead of raising
    ValueError: Handler name collision.
    """

    class Base(RoutingClass):
        def __init__(self):
            self.main = Router(self, name="main")

        @route()
        def index(self):
            return "BASE"

    class Derived(Base):
        @route()
        def index(self):
            return "DERIVED"

    # Should not raise ValueError: Handler name collision
    d = Derived()
    # Derived.index should be used, not Base.index
    assert d.main.node("index")() == "DERIVED"
    # Verify only one entry registered
    info = d.main.nodes()
    assert len(info.get("entries", {})) == 1


def test_router_node_and_nodes_structure():
    """Test node() and nodes() work correctly."""
    svc = ManualService()
    # auto is marked with @route, so it's available
    assert svc.api.node("auto")() == "auto"
    tree = svc.api.nodes()
    assert tree["entries"]
    assert "routers" not in tree


def test_inherit_plugins_branches():
    parent = ManualService()
    child = ManualService()
    parent.api.plug("stamp_extra")
    before = len(child.api._plugins_by_name)
    child.api._on_attached_to_parent(parent.api)
    after = len(child.api._plugins_by_name)
    assert after > before
    child.api._on_attached_to_parent(parent.api)
    assert len(child.api._plugins_by_name) == after
    # Force missing plugin bucket to exercise seed path
    parent.api._plugin_info.pop("stamp_extra", None)
    child.api._on_attached_to_parent(parent.api)

    orphan = ManualService()
    plain = ManualService()
    plain_before = len(orphan.api._plugins_by_name)
    orphan.api._on_attached_to_parent(plain.api)
    assert len(orphan.api._plugins_by_name) == plain_before


def test_inherit_plugins_seed_from_empty_parent_bucket():
    parent = ManualService()
    parent.api.plug("stamp_extra")
    parent.api._plugin_info.pop("stamp_extra", None)
    child = ManualService()
    child.api._on_attached_to_parent(parent.api)
    # Config is now a callable lookup, verify plugin is accessible
    assert "stamp_extra" in child.api._plugins_by_name


def test_router_nodes_include_metadata_tree():
    parent = ManualService()
    parent.api.add_entry(parent.first)
    info = parent.api.nodes()
    assert "entries" in info


def test_router_nodes_with_basepath():
    """Test nodes() with basepath navigates to child router."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Grandchild(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def grandchild_action(self):
            return "grandchild"

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.child.grandchild = Grandchild()
            self.api.attach_instance(self.child, name="child")
            self.child.api.attach_instance(self.child.grandchild, name="grandchild")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Without basepath - returns full tree
    full = root.api.nodes()
    assert "root_action" in full["entries"]
    assert "child" in full["routers"]

    # With basepath="child" - returns child subtree
    child_nodes = root.api.nodes(basepath="child")
    assert child_nodes["name"] == "api"
    assert "child_action" in child_nodes["entries"]
    assert "grandchild" in child_nodes["routers"]
    assert "root_action" not in child_nodes.get("entries", {})

    # With basepath="child/grandchild" - returns grandchild subtree
    grandchild_nodes = root.api.nodes(basepath="child/grandchild")
    assert grandchild_nodes["name"] == "api"
    assert "grandchild_action" in grandchild_nodes["entries"]
    assert "routers" not in grandchild_nodes  # no children

    # With basepath pointing to a handler - returns empty dict
    handler_nodes = root.api.nodes(basepath="root_action")
    assert handler_nodes == {}

    # With basepath pointing to non-existent path - returns empty dict
    missing_nodes = root.api.nodes(basepath="nonexistent")
    assert missing_nodes == {}


def test_nodes_lazy_returns_router_references():
    """Test nodes(lazy=True) returns router references for child routers."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Without lazy - routers dict contains expanded nodes
    full = root.api.nodes()
    assert isinstance(full["routers"]["child"], dict)
    assert "child_action" in full["routers"]["child"]["entries"]

    # With lazy=True - routers dict contains router references (not expanded)
    lazy_nodes = root.api.nodes(lazy=True)
    child_router = lazy_nodes["routers"]["child"]
    assert isinstance(child_router, Router)

    # To expand, call nodes() on the router or use basepath
    child_nodes = child_router.nodes()
    assert isinstance(child_nodes, dict)
    assert "child_action" in child_nodes["entries"]

    # Or use basepath from parent
    child_via_basepath = root.api.nodes(basepath="child")
    assert "child_action" in child_via_basepath["entries"]


def test_openapi_returns_schema():
    """Test openapi() returns OpenAPI-compatible schema."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_user(self, user_id: int, name: str = "default") -> dict:
            """Get a user by ID."""
            return {"id": user_id, "name": name}

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="users")

        @route("api")
        def health(self) -> str:
            """Health check endpoint."""
            return "ok"

    root = Root()

    # Full schema (non-lazy)
    schema = root.api.nodes(mode="openapi")
    assert "paths" in schema
    assert "/health" in schema["paths"]
    assert "/users/get_user" in schema["paths"]

    # Check health endpoint - no params + return means GET
    health_op = schema["paths"]["/health"]["get"]
    assert health_op["operationId"] == "health"
    assert health_op["summary"] == "Health check endpoint."

    # Check user endpoint with parameters - has params means POST
    user_op = schema["paths"]["/users/get_user"]["post"]
    assert user_op["operationId"] == "get_user"
    assert "parameters" in user_op or "requestBody" in user_op


def test_openapi_lazy_returns_router_references():
    """Test openapi(lazy=True) returns router references for child routers."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            return "child"

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Lazy mode - returns router references
    lazy_schema = root.api.nodes(mode="openapi", lazy=True)
    assert "/root_action" in lazy_schema["paths"]
    assert "routers" in lazy_schema
    assert isinstance(lazy_schema["routers"]["child"], Router)

    # Expand child via basepath - paths are absolute from root
    child_schema = root.api.nodes(basepath="child", mode="openapi")
    assert "/child/action" in child_schema["paths"]


def test_openapi_with_basepath():
    """Test openapi(basepath=...) navigates to child with absolute paths."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Get schema starting from child - paths include basepath prefix (issue #16)
    child_schema = root.api.nodes(mode="openapi", basepath="child")
    assert "/child/child_action" in child_schema["paths"]
    assert "/root_action" not in child_schema.get("paths", {})


def test_openapi_basepath_absolute_paths_issue_16():
    """Test that basepath produces absolute paths from root (issue #16).

    When using nodes(basepath="shop", mode="openapi"), the paths should be
    absolute from the root (/shop/purchase/list) not relative (/purchase/list).
    This is required for Swagger UI "Try it out" to work correctly.
    """

    class PurchaseService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def list(self) -> list:
            """List all purchases."""
            return []

        @route("api")
        def create(self, item: str, qty: int = 1) -> dict:
            """Create a purchase."""
            return {"item": item, "qty": qty}

    class Shop(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.purchase = PurchaseService()
            self.api.attach_instance(self.purchase, name="purchase")

        @route("api")
        def info(self) -> dict:
            """Shop info."""
            return {"name": "My Shop"}

    shop = Shop()

    # Get OpenAPI for purchase subtree via basepath
    purchase_schema = shop.api.nodes(basepath="purchase", mode="openapi")

    # Paths must be absolute from root (include /purchase prefix)
    assert "/purchase/list" in purchase_schema["paths"]
    assert "/purchase/create" in purchase_schema["paths"]

    # Verify operations are correct
    list_op = purchase_schema["paths"]["/purchase/list"]["get"]
    assert list_op["operationId"] == "list"
    assert list_op["summary"] == "List all purchases."

    create_op = purchase_schema["paths"]["/purchase/create"]["post"]
    assert create_op["operationId"] == "create"
    assert "requestBody" in create_op  # Has parameters, so POST with body

    # Root handlers should NOT be included
    assert "/info" not in purchase_schema["paths"]
    assert "/purchase/info" not in purchase_schema["paths"]


def test_configure_validates_inputs_and_targets():
    svc = LoggingService()
    with pytest.raises(ValueError):
        svc.routing.configure([], enabled=True)
    with pytest.raises(ValueError):
        svc.routing.configure({"flags": "on"})
    with pytest.raises(TypeError):
        svc.routing.configure(42)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.routing.configure("?", foo="bar")
    with pytest.raises(ValueError):
        svc.routing.configure("missingcolon", mode="x")
    with pytest.raises(ValueError):
        svc.routing.configure(":logging/_all_", mode="x")
    with pytest.raises(ValueError):
        svc.routing.configure("api:/_all_", mode="x")
    with pytest.raises(AttributeError):
        svc.routing.configure("api:ghost/_all_", flags="on")
    with pytest.raises(ValueError):
        svc.routing.configure("api:logging/_all_")
    with pytest.raises(KeyError):
        svc.routing.configure("api:logging/missing*", flags="before")
    result = svc.routing.configure("api:logging", flags="before")
    assert result["updated"] == ["_all_"]


def test_configure_question_success_and_router_proxy_errors():
    svc = LoggingService()
    tree = svc.routing.configure("?")
    assert "api" in tree
    with pytest.raises(AttributeError):
        svc.routing.get_router("missing")
    svc._routers.pop("api")
    router = svc.routing.get_router("api")
    assert router is svc.api


def test_iter_registered_routers_lists_entries():
    svc = ManualService()
    pairs = list(svc._iter_registered_routers())
    assert pairs and pairs[0][0] == "api"


def test_get_router_skips_empty_segments():
    class Leaf(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="leaf")

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Leaf()
            self.api._children["child"] = self.child.api  # direct attach for test

    svc = Parent()
    router = svc.routing.get_router("api/child//")
    assert router.name == "leaf"


def test_is_routing_class_helper():
    svc = ManualService()
    assert is_routing_class(svc) is True
    assert is_routing_class(object()) is False


def test_openapi_basepath_to_handler_returns_empty():
    """Test openapi(basepath=...) returns empty when pointing to handler."""

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            return "ok"

    root = Root()

    # basepath pointing to handler returns empty (handler is not a router)
    result = root.api.nodes(mode="openapi", basepath="action")
    assert result == {}

    # basepath pointing to non-existent path also returns empty
    result = root.api.nodes(mode="openapi", basepath="nonexistent")
    assert result == {}


def test_openapi_with_pydantic_model():
    """Test openapi() uses pydantic model schema when available."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def get_user(self, user_id: int, name: str = "default") -> dict:
            """Get a user by ID."""
            return {"id": user_id, "name": name}

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # Should have requestBody with pydantic schema
    # Method is POST because handler has params
    path_item = schema["paths"]["/get_user"]
    assert "post" in path_item
    operation = path_item["post"]
    assert "requestBody" in operation
    assert operation["requestBody"]["required"] is True
    assert "content" in operation["requestBody"]
    assert "application/json" in operation["requestBody"]["content"]


def test_openapi_handler_without_type_hints():
    """Test openapi() handles handlers without type hints."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def no_hints(self, arg):
            """No type hints here."""
            return arg

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    path_item = schema["paths"]["/no_hints"]
    # Without type hints, get_type_hints returns empty → no params, no return → POST
    operation = path_item["post"]
    # Should have default response but no parameters
    assert "responses" in operation
    assert "200" in operation["responses"]


def test_openapi_type_conversion():
    """Test pydantic schema handles various types in requestBody."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def typed_params(self, s: str, i: int, f: float, b: bool, items: list, data: dict) -> str:
            return "ok"

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # POST uses requestBody with pydantic schema
    operation = schema["paths"]["/typed_params"]["post"]
    json_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    props = json_schema["properties"]

    # Check all types are in schema properties
    assert props["s"]["type"] == "string"
    assert props["i"]["type"] == "integer"
    assert props["f"]["type"] == "number"
    assert props["b"]["type"] == "boolean"
    assert props["items"]["type"] == "array"
    assert props["data"]["type"] == "object"


def test_openapi_generic_types():
    """Test pydantic schema handles generic types like list[str]."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def generic_params(self, items: list[str], data: dict[str, int]) -> list[str]:
            return items

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # POST uses requestBody with pydantic schema
    operation = schema["paths"]["/generic_params"]["post"]
    json_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    props = json_schema["properties"]

    # Generic types should be properly typed by pydantic
    assert props["items"]["type"] == "array"
    assert props["data"]["type"] == "object"


def test_openapi_unknown_type_graceful_fallback():
    """Test openapi gracefully handles types pydantic can't process."""

    class CustomType:
        pass

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def custom_param(self, obj: CustomType) -> CustomType:
            return obj

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # Pydantic can't handle arbitrary types without special config
    # So operation won't have requestBody, but should still work
    operation = schema["paths"]["/custom_param"]["post"]
    assert operation["operationId"] == "custom_param"
    # No requestBody because pydantic failed, but we have default response
    assert "responses" in operation


def test_openapi_required_vs_optional_params():
    """Test pydantic schema correctly marks required vs optional in requestBody."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def mixed_params(self, required: int, optional: str = "default"):
            return "ok"

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # Has params → POST with requestBody
    operation = schema["paths"]["/mixed_params"]["post"]
    json_schema = operation["requestBody"]["content"]["application/json"]["schema"]

    # Check required fields in pydantic schema
    required_fields = json_schema.get("required", [])
    assert "required" in required_fields
    assert "optional" not in required_fields


def test_openapi_handles_broken_type_hints():
    """Test openapi() gracefully handles functions with unresolvable type hints."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Service()

    # Manually break the function's type hints by adding unresolvable annotation
    entry = svc.api._entries["handler"]
    original_func = entry.func

    # Create a wrapper with broken annotations
    def broken_hints():
        return "ok"

    broken_hints.__annotations__ = {"arg": "NonExistentType", "return": "AlsoMissing"}
    entry.func = broken_hints

    # Should not raise, should fall back gracefully
    schema = svc.api.nodes(mode="openapi")
    assert "/handler" in schema["paths"]

    # Restore
    entry.func = original_func


def test_openapi_handles_hint_param_mismatch():
    """Test openapi() when type hint references non-existent parameter."""

    class Service(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self, real_param: int):
            return "ok"

    svc = Service()

    # Manually modify the entry's func annotations to have a mismatch
    entry = svc.api._entries["handler"]
    original_func = entry.func

    # Create a function with mismatched hint/signature
    def mismatched():
        pass

    # Add hint for param not in signature (signature has no params)
    mismatched.__annotations__ = {"ghost_param": int}
    entry.func = mismatched

    # Should not raise, should skip the mismatched param
    schema = svc.api.nodes(mode="openapi")
    # Has param hints → POST (even if mismatched)
    operation = schema["paths"]["/handler"]["post"]
    # No parameters should be added since ghost_param isn't in signature
    assert "parameters" not in operation or len(operation.get("parameters", [])) == 0

    # Restore
    entry.func = original_func


def test_nodes_unknown_mode_raises():
    """Test that nodes(mode='unknown') raises ValueError."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            pass

    svc = Svc()

    with pytest.raises(ValueError, match="Unknown mode: unknown"):
        svc.api.nodes(mode="unknown")


# -----------------------------------------------------------------------------
# h_openapi mode tests
# -----------------------------------------------------------------------------


def test_h_openapi_returns_hierarchical_schema():
    """Test h_openapi mode returns nested OpenAPI structure."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_user(self, user_id: int) -> dict:
            """Get a user by ID."""
            return {"id": user_id}

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="users")

        @route("api")
        def health(self) -> str:
            """Health check endpoint."""
            return "ok"

    root = Root()

    # Hierarchical schema
    schema = root.api.nodes(mode="h_openapi")

    # Root level has paths for its own entries
    assert "paths" in schema
    assert "/health" in schema["paths"]
    # But NOT the child paths (those are nested)
    assert "/users/get_user" not in schema["paths"]

    # Child routers are nested, not flattened
    assert "routers" in schema
    assert "users" in schema["routers"]

    # Child has its own paths
    child_schema = schema["routers"]["users"]
    assert "paths" in child_schema
    assert "/get_user" in child_schema["paths"]


def test_h_openapi_vs_openapi_comparison():
    """Test difference between h_openapi (hierarchical) and openapi (flat)."""

    class GrandChild(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def deep_action(self):
            return "deep"

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.grandchild = GrandChild()
            self.api.attach_instance(self.grandchild, name="grand")

        @route("api")
        def child_action(self):
            return "child"

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Flat openapi - all paths at top level
    flat = root.api.nodes(mode="openapi")
    assert "/root_action" in flat["paths"]
    assert "/child/child_action" in flat["paths"]
    assert "/child/grand/deep_action" in flat["paths"]
    assert "routers" not in flat  # No routers in eager flat mode

    # Hierarchical h_openapi - paths nested
    hier = root.api.nodes(mode="h_openapi")
    assert "/root_action" in hier["paths"]
    assert "/child/child_action" not in hier["paths"]  # Not at root level
    assert "routers" in hier

    # Navigate the hierarchy
    child_hier = hier["routers"]["child"]
    assert "/child_action" in child_hier["paths"]
    assert "/grand/deep_action" not in child_hier["paths"]  # Not at child level
    assert "routers" in child_hier

    grand_hier = child_hier["routers"]["grand"]
    assert "/deep_action" in grand_hier["paths"]


def test_h_openapi_lazy_returns_router_references():
    """Test h_openapi lazy=True returns router references."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            return "child"

    class Root(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Lazy h_openapi
    lazy = root.api.nodes(mode="h_openapi", lazy=True)
    assert "/root_action" in lazy["paths"]
    assert "routers" in lazy
    # In lazy mode, child is a Router reference
    assert isinstance(lazy["routers"]["child"], Router)

    # Can expand via basepath - paths are absolute from root
    child_schema = root.api.nodes(basepath="child", mode="h_openapi")
    assert "/child/action" in child_schema["paths"]


def test_h_openapi_preserves_openapi_format():
    """Test h_openapi produces valid OpenAPI format for entries."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def create_item(self, name: str, count: int = 1) -> dict:
            """Create a new item."""
            return {"name": name, "count": count}

    svc = Svc()
    schema = svc.api.nodes(mode="h_openapi")

    # Check OpenAPI structure - has params means POST with requestBody
    path_item = schema["paths"]["/create_item"]
    assert "post" in path_item
    operation = path_item["post"]
    assert operation["operationId"] == "create_item"
    assert operation["summary"] == "Create a new item."
    assert "requestBody" in operation


def test_h_openapi_empty_routers_excluded():
    """Test h_openapi excludes empty routers dict."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            return "ok"

    svc = Svc()
    schema = svc.api.nodes(mode="h_openapi")

    # No children, so no routers key
    assert "paths" in schema
    assert "routers" not in schema


def test_nodes_includes_description_and_owner_doc():
    """Test nodes() includes router description and owner docstring."""

    class ArticleService(RoutingClass):
        """Service for managing articles."""

        def __init__(self):
            self.api = Router(self, name="api", description="API for articles")

        @route("api")
        def list_articles(self):
            return []

    svc = ArticleService()
    nodes = svc.api.nodes()

    assert nodes["description"] == "API for articles"
    assert nodes["owner_doc"] == "Service for managing articles."


def test_nodes_description_none_when_not_set():
    """Test nodes() returns None for description when not set."""

    class SimpleService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            pass

    svc = SimpleService()
    nodes = svc.api.nodes()

    assert nodes["description"] is None
    assert nodes["owner_doc"] is None  # No docstring on class


def test_h_openapi_includes_description_and_owner_doc():
    """Test h_openapi mode includes description and owner_doc at each level."""

    class ChildService(RoutingClass):
        """Child service for users."""

        def __init__(self):
            self.api = Router(self, name="api", description="User management")

        @route("api")
        def get_user(self):
            return {}

    class RootService(RoutingClass):
        """Main API service."""

        def __init__(self):
            self.api = Router(self, name="api", description="Main API")
            self.users = ChildService()
            self.api.attach_instance(self.users, name="users")

        @route("api")
        def health(self):
            return "ok"

    root = RootService()
    schema = root.api.nodes(mode="h_openapi")

    # Root level
    assert schema["description"] == "Main API"
    assert schema["owner_doc"] == "Main API service."

    # Child level
    child_schema = schema["routers"]["users"]
    assert child_schema["description"] == "User management"
    assert child_schema["owner_doc"] == "Child service for users."


# -----------------------------------------------------------------------------
# HTTP method guessing tests
# -----------------------------------------------------------------------------
# Current logic:
# - Has parameters → POST
# - No parameters, no return → POST (side effect)
# - No parameters, has return → GET (read operation)


def test_guess_http_method_no_params_with_return_is_get():
    """Test guess_http_method returns GET for no-param functions with return."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    def no_params() -> str:
        return "ok"

    assert OpenAPITranslator.guess_http_method(no_params) == "get"


def test_guess_http_method_no_params_no_return_is_post():
    """Test guess_http_method returns POST for no-param functions without return."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    def no_params_no_return():
        pass

    def no_params_none_return() -> None:
        pass

    assert OpenAPITranslator.guess_http_method(no_params_no_return) == "post"
    assert OpenAPITranslator.guess_http_method(no_params_none_return) == "post"


def test_guess_http_method_with_params_is_post():
    """Test guess_http_method returns POST for functions with params."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    def scalar_params(name: str, count: int) -> str:
        return "ok"

    def complex_params(items: list) -> list:
        return items

    # Any params → POST
    assert OpenAPITranslator.guess_http_method(scalar_params) == "post"
    assert OpenAPITranslator.guess_http_method(complex_params) == "post"


def test_guess_http_method_broken_hints_is_post():
    """Test guess_http_method returns POST when hints can't be resolved."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    def broken():
        return "ok"

    # Manually break annotations
    broken.__annotations__ = {"arg": "NonExistentType"}

    # Should default to POST (safer)
    assert OpenAPITranslator.guess_http_method(broken) == "post"


def test_openapi_uses_guessed_http_method():
    """Test openapi output uses guessed HTTP method from signature."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_item(self, item_id: int) -> dict:
            """Get an item - should be POST (has params)."""
            return {"id": item_id}

        @route("api")
        def create_item(self, data: dict) -> dict:
            """Create an item - should be POST (has params)."""
            return data

        @route("api")
        def list_items(self) -> list:
            """List items - should be GET (no params, has return)."""
            return []

        @route("api")
        def reset_cache(self):
            """Reset cache - should be POST (no params, no return = side effect)."""
            pass

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # POST for params (any type)
    assert "post" in schema["paths"]["/get_item"]
    assert "post" in schema["paths"]["/create_item"]

    # GET for no params with return
    assert "get" in schema["paths"]["/list_items"]
    assert "post" not in schema["paths"]["/list_items"]

    # POST for no params, no return (side effect)
    assert "post" in schema["paths"]["/reset_cache"]
    assert "get" not in schema["paths"]["/reset_cache"]


# -----------------------------------------------------------------------------
# OpenAPI plugin tests
# -----------------------------------------------------------------------------


def test_openapi_plugin_method_override():
    """Test openapi plugin allows explicit HTTP method override."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("openapi")

        @route("api", openapi_method="delete")
        def remove_item(self, item_id: int) -> dict:
            """Delete an item - explicitly DELETE despite scalar params."""
            return {"deleted": item_id}

        @route("api", openapi_method="PUT")
        def update_item(self, item_id: int, name: str) -> dict:
            """Update an item - explicitly PUT."""
            return {"id": item_id, "name": name}

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # Override to DELETE
    assert "delete" in schema["paths"]["/remove_item"]
    assert "get" not in schema["paths"]["/remove_item"]

    # Override to PUT (case insensitive)
    assert "put" in schema["paths"]["/update_item"]


def test_openapi_plugin_tags():
    """Test openapi plugin adds tags to operations."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("openapi")

        @route("api", openapi_tags=["users", "admin"])
        def admin_action(self) -> str:
            return "ok"

        @route("api", openapi_tags="public")
        def public_action(self) -> str:
            return "ok"

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # List of tags
    admin_op = schema["paths"]["/admin_action"]["get"]
    assert admin_op["tags"] == ["users", "admin"]

    # Single tag (converted to list)
    public_op = schema["paths"]["/public_action"]["get"]
    assert public_op["tags"] == ["public"]


def test_openapi_plugin_no_effect_without_config():
    """Test openapi plugin doesn't change anything without explicit config."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("openapi")

        @route("api")
        def get_item(self, item_id: int) -> dict:
            """Should still use guessed method (POST because has params)."""
            return {"id": item_id}

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # Method should be guessed as POST (has params, not overridden)
    assert "post" in schema["paths"]["/get_item"]


def test_openapi_plugin_available():
    """Test openapi plugin is registered and available."""
    assert "openapi" in Router.available_plugins()


# -----------------------------------------------------------------------------
# node() method tests
# -----------------------------------------------------------------------------


def test_node_returns_entry_info():
    """Test node() returns RouterNode for a single entry."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_item(self, item_id: int) -> dict:
            """Get an item by ID."""
            return {"id": item_id}

    svc = Svc()
    node = svc.api.node("get_item")

    assert node.path == "get_item"
    assert node.doc == "Get an item by ID."
    assert node.metadata is not None


# -----------------------------------------------------------------------------
# TypedDict response schema tests
# -----------------------------------------------------------------------------


def test_openapi_typeddict_response_schema():
    """Test openapi generates schema from TypedDict return type."""
    from typing import TypedDict

    class UserResponse(TypedDict):
        id: int
        name: str
        active: bool

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_user(self) -> UserResponse:
            """Get user info."""
            return {"id": 1, "name": "test", "active": True}

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # No params + return = GET
    operation = schema["paths"]["/get_user"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    # Should have TypedDict fields as properties
    assert response_schema["type"] == "object"
    assert "properties" in response_schema
    assert response_schema["properties"]["id"]["type"] == "integer"
    assert response_schema["properties"]["name"]["type"] == "string"
    assert response_schema["properties"]["active"]["type"] == "boolean"


def test_openapi_typeddict_with_required_keys():
    """Test openapi includes required keys from TypedDict."""
    from typing import TypedDict, NotRequired

    class PartialUser(TypedDict, total=False):
        id: int
        name: str

    class FullUser(TypedDict):
        id: int
        name: str

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_full_user(self) -> FullUser:
            """All fields required."""
            return {"id": 1, "name": "test"}

        @route("api")
        def get_partial_user(self) -> PartialUser:
            """No fields required (total=False)."""
            return {}

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # Full user has required keys
    full_schema = schema["paths"]["/get_full_user"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "required" in full_schema
    assert set(full_schema["required"]) == {"id", "name"}

    # Partial user has no required keys
    partial_schema = schema["paths"]["/get_partial_user"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "required" not in partial_schema or len(partial_schema.get("required", [])) == 0


def test_openapi_non_typeddict_still_works():
    """Test openapi still works for non-TypedDict return types."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_string(self) -> str:
            return "ok"

        @route("api")
        def get_list(self) -> list:
            return []

        @route("api")
        def get_dict(self) -> dict:
            return {}

    svc = Svc()
    schema = svc.api.nodes(mode="openapi")

    # Simple types still work
    str_schema = schema["paths"]["/get_string"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert str_schema["type"] == "string"

    list_schema = schema["paths"]["/get_list"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert list_schema["type"] == "array"

    dict_schema = schema["paths"]["/get_dict"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert dict_schema["type"] == "object"
