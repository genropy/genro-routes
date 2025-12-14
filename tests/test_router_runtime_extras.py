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

import pytest

from genro_routes import RoutedClass, Router, route
from genro_routes.core.routed import is_routed_class
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class ManualService(RoutedClass):
    """Service with manual router registration."""

    def __init__(self):
        self.api = Router(self, name="api", auto_discover=False)

    def first(self):
        return "first"

    def second(self):
        return "second"

    @route("api", marker="yes")
    def auto(self):
        return "auto"


class DualRoutes(RoutedClass):
    def __init__(self):
        self.one = Router(self, name="one", auto_discover=False)
        self.two = Router(self, name="two", auto_discover=False)

    @route("one")
    @route("two", name="two_alias")
    def shared(self):
        return "shared"


class MultiChild(RoutedClass):
    def __init__(self):
        self.router_a = Router(self, name="router_a", auto_discover=False)
        self.router_b = Router(self, name="router_b", auto_discover=False)


class SlotRouted(RoutedClass):
    __slots__ = ("slot_router",)

    def __init__(self):
        self.slot_router = Router(self, name="slot", auto_discover=False)


class DuplicateMarkers(RoutedClass):
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


class LoggingService(RoutedClass):
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
    assert "first" in svc.api._handlers
    assert "second" in svc.api._handlers

    svc.api.add_entry("first, second", replace=True)
    before = set(svc.api._handlers.keys())
    assert svc.api.add_entry("   ") is svc.api
    assert set(svc.api._handlers.keys()) == before

    with pytest.raises(TypeError):
        svc.api.add_entry(123)

    svc.api.add_entry("*", metadata={"source": "wild"})
    entry = svc.api._entries["auto"]
    assert entry.metadata["marker"] == "yes"
    assert entry.metadata["source"] == "wild"


def test_plugin_on_decore_runs_for_existing_entries():
    svc = ManualService()
    svc.api.plug("stamp_extra")
    svc.api.add_entry(svc.first, name="alias_first")
    assert svc.api._entries["alias_first"].metadata["stamped"] is True


def test_iter_marked_methods_skip_other_router_markers():
    svc = DualRoutes()
    svc.one.add_entry("*")
    svc.two.add_entry("*")
    assert "shared" in svc.one._handlers
    assert "two_alias" in svc.two._handlers


def test_iter_marked_methods_deduplicate_same_function():
    svc = DuplicateMarkers()
    assert svc.api.get("original")() == "ok"
    assert len(svc.api._handlers) == 1


def test_router_call_and_nodes_structure():
    svc = ManualService()
    svc.api.add_entry(svc.first)
    assert svc.api.call("first") == "first"
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

    class Child(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Grandchild(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def grandchild_action(self):
            return "grandchild"

    class Root(RoutedClass):
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


def test_get_returns_child_router():
    """Test get() returns child router when path points to one."""

    class Child(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Root(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # get() returns handler when path points to handler
    handler = root.api.get("root_action")
    assert callable(handler)
    assert handler() == "root"

    # get() returns child router when path points to router
    child_router = root.api.get("child")
    assert isinstance(child_router, Router)
    assert child_router.name == "api"

    # get() returns None when path doesn't exist
    result = root.api.get("nonexistent")
    assert result is None

    # get() with path into child still works
    child_handler = root.api.get("child/child_action")
    assert callable(child_handler)
    assert child_handler() == "child"


def test_nodes_lazy_returns_callables():
    """Test nodes(lazy=True) returns callables for child routers."""

    class Child(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Root(RoutedClass):
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

    # With lazy=True - routers dict contains callables
    lazy_nodes = root.api.nodes(lazy=True)
    assert callable(lazy_nodes["routers"]["child"])

    # Calling the callable expands the child nodes
    child_nodes = lazy_nodes["routers"]["child"]()
    assert isinstance(child_nodes, dict)
    assert "child_action" in child_nodes["entries"]


def test_openapi_returns_schema():
    """Test openapi() returns OpenAPI-compatible schema."""

    class Child(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_user(self, user_id: int, name: str = "default") -> dict:
            """Get a user by ID."""
            return {"id": user_id, "name": name}

    class Root(RoutedClass):
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

    # Check health endpoint
    health_op = schema["paths"]["/health"]["post"]
    assert health_op["operationId"] == "health"
    assert health_op["summary"] == "Health check endpoint."

    # Check user endpoint with parameters
    user_op = schema["paths"]["/users/get_user"]["post"]
    assert user_op["operationId"] == "get_user"
    assert "parameters" in user_op or "requestBody" in user_op


def test_openapi_lazy_returns_callables():
    """Test openapi(lazy=True) returns callables for child routers."""

    class Child(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            return "child"

    class Root(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Lazy mode
    lazy_schema = root.api.nodes(mode="openapi", lazy=True)
    assert "/root_action" in lazy_schema["paths"]
    assert "routers" in lazy_schema
    assert callable(lazy_schema["routers"]["child"])

    # Expand child
    child_schema = lazy_schema["routers"]["child"]()
    assert "/child/action" in child_schema["paths"]


def test_openapi_with_basepath():
    """Test openapi(basepath=...) navigates to child."""

    class Child(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_action(self):
            return "child"

    class Root(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def root_action(self):
            return "root"

    root = Root()

    # Get schema starting from child
    child_schema = root.api.nodes(mode="openapi", basepath="child")
    assert "/child/child_action" in child_schema["paths"]
    assert "/root_action" not in child_schema["paths"]


def test_configure_validates_inputs_and_targets():
    svc = LoggingService()
    with pytest.raises(ValueError):
        svc.routedclass.configure([], enabled=True)
    with pytest.raises(ValueError):
        svc.routedclass.configure({"flags": "on"})
    with pytest.raises(TypeError):
        svc.routedclass.configure(42)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.routedclass.configure("?", foo="bar")
    with pytest.raises(ValueError):
        svc.routedclass.configure("missingcolon", mode="x")
    with pytest.raises(ValueError):
        svc.routedclass.configure(":logging/_all_", mode="x")
    with pytest.raises(ValueError):
        svc.routedclass.configure("api:/_all_", mode="x")
    with pytest.raises(AttributeError):
        svc.routedclass.configure("api:ghost/_all_", flags="on")
    with pytest.raises(ValueError):
        svc.routedclass.configure("api:logging/_all_")
    with pytest.raises(KeyError):
        svc.routedclass.configure("api:logging/missing*", flags="before")
    result = svc.routedclass.configure("api:logging", flags="before")
    assert result["updated"] == ["_all_"]


def test_configure_question_success_and_router_proxy_errors():
    svc = LoggingService()
    tree = svc.routedclass.configure("?")
    assert "api" in tree
    with pytest.raises(AttributeError):
        svc.routedclass.get_router("missing")
    svc._routers.pop("api")
    router = svc.routedclass.get_router("api")
    assert router is svc.api


def test_iter_registered_routers_lists_entries():
    svc = ManualService()
    pairs = list(svc._iter_registered_routers())
    assert pairs and pairs[0][0] == "api"


def test_get_router_skips_empty_segments():
    class Leaf(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="leaf", auto_discover=False)

    class Parent(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Leaf()
            self.api._children["child"] = self.child.api  # direct attach for test

    svc = Parent()
    router = svc.routedclass.get_router("api/child//")
    assert router.name == "leaf"


def test_is_routed_class_helper():
    svc = ManualService()
    assert is_routed_class(svc) is True
    assert is_routed_class(object()) is False


def test_openapi_basepath_to_handler_returns_empty():
    """Test openapi(basepath=...) returns empty when pointing to handler."""

    class Root(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def action(self):
            return "ok"

    root = Root()

    # basepath pointing to handler returns empty schema
    result = root.api.nodes(mode="openapi", basepath="action")
    assert result == {"paths": {}, "routers": {}}

    # basepath pointing to non-existent path also returns empty
    result = root.api.nodes(mode="openapi", basepath="nonexistent")
    assert result == {"paths": {}, "routers": {}}


def test_openapi_with_pydantic_model():
    """Test openapi() uses pydantic model schema when available."""
    from genro_routes.plugins.pydantic import PydanticPlugin

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def get_user(self, user_id: int, name: str = "default") -> dict:
            """Get a user by ID."""
            return {"id": user_id, "name": name}

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # Should have requestBody with pydantic schema
    path_item = schema["paths"]["/get_user"]
    assert "post" in path_item
    operation = path_item["post"]
    assert "requestBody" in operation
    assert operation["requestBody"]["required"] is True
    assert "content" in operation["requestBody"]
    assert "application/json" in operation["requestBody"]["content"]


def test_openapi_entry_filtering():
    """Test openapi() respects plugin filtering."""

    class FilterPlugin(BasePlugin):
        plugin_code = "openapi_filter"
        plugin_description = "Filters entries for testing"

        def allow_entry(self, router, entry, **kwargs):
            return entry.name != "blocked"

    if "openapi_filter" not in Router.available_plugins():
        Router.register_plugin(FilterPlugin)

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("openapi_filter")

        @route("api")
        def allowed(self):
            return "ok"

        @route("api")
        def blocked(self):
            return "blocked"

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    # blocked entry should be filtered out
    assert "/allowed" in schema["paths"]
    assert "/blocked" not in schema["paths"]


def test_openapi_handler_without_type_hints():
    """Test openapi() handles handlers without type hints."""

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def no_hints(self, arg):
            """No type hints here."""
            return arg

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    path_item = schema["paths"]["/no_hints"]
    operation = path_item["post"]
    # Should have default response but no parameters
    assert "responses" in operation
    assert "200" in operation["responses"]


def test_openapi_type_conversion():
    """Test _python_type_to_openapi handles various types."""

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def typed_params(
            self, s: str, i: int, f: float, b: bool, items: list, data: dict
        ) -> str:
            return "ok"

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    operation = schema["paths"]["/typed_params"]["post"]
    params = operation["parameters"]

    # Check all types are converted
    param_types = {p["name"]: p["schema"]["type"] for p in params}
    assert param_types["s"] == "string"
    assert param_types["i"] == "integer"
    assert param_types["f"] == "number"
    assert param_types["b"] == "boolean"
    assert param_types["items"] == "array"
    assert param_types["data"] == "object"


def test_openapi_generic_types():
    """Test openapi() handles generic types like List[str]."""
    from typing import List, Dict

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def generic_params(self, items: List[str], data: Dict[str, int]) -> List[str]:
            return items

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    operation = schema["paths"]["/generic_params"]["post"]
    params = operation["parameters"]

    # Generic types should map to their origin type
    param_types = {p["name"]: p["schema"]["type"] for p in params}
    assert param_types["items"] == "array"
    assert param_types["data"] == "object"


def test_openapi_unknown_type_defaults_to_object():
    """Test openapi() defaults unknown types to object."""

    class CustomType:
        pass

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def custom_param(self, obj: CustomType) -> CustomType:
            return obj

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    operation = schema["paths"]["/custom_param"]["post"]
    params = operation["parameters"]

    # Unknown type should default to "object"
    assert params[0]["schema"]["type"] == "object"


def test_openapi_required_vs_optional_params():
    """Test openapi() correctly marks required vs optional parameters."""

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def mixed_params(self, required: int, optional: str = "default"):
            return "ok"

    svc = Service()
    schema = svc.api.nodes(mode="openapi")

    operation = schema["paths"]["/mixed_params"]["post"]
    params = operation["parameters"]

    required_param = next(p for p in params if p["name"] == "required")
    optional_param = next(p for p in params if p["name"] == "optional")

    assert required_param["required"] is True
    assert optional_param["required"] is False


def test_openapi_handles_broken_type_hints():
    """Test openapi() gracefully handles functions with unresolvable type hints."""
    from genro_routes.core.base_router import BaseRouter

    class Service(RoutedClass):
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
    from genro_routes.core.base_router import MethodEntry

    class Service(RoutedClass):
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
    operation = schema["paths"]["/handler"]["post"]
    # No parameters should be added since ghost_param isn't in signature
    assert "parameters" not in operation or len(operation.get("parameters", [])) == 0

    # Restore
    entry.func = original_func


def test_nodes_unknown_mode_raises():
    """Test that nodes(mode='unknown') raises ValueError."""

    class Svc(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            pass

    svc = Svc()

    with pytest.raises(ValueError, match="Unknown mode: unknown"):
        svc.api.nodes(mode="unknown")
