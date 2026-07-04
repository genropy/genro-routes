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
from typing import TypedDict

import pytest

from genro_routes import Router, RoutingClass, route
from genro_routes.core.routing import is_routing_class
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry

# TypedDict classes at module level for cross-Python-version compatibility
# (pydantic handles TypedDict differently when defined inside functions
# on Python <3.12). Tests using these are skipped on <3.12.

class _UserResponse(TypedDict):
    id: int
    name: str
    active: bool


class ManualService(RoutingClass):
    """Service using the auto-created single router."""

    def first(self):
        return "first"

    def second(self):
        return "second"

    @route(marker="yes")
    def auto(self):
        return "auto"


class SlotRouted(RoutingClass):
    __slots__ = ("slot_router",)

    def __init__(self):
        self.slot_router = Router(self)


class DuplicateMarkers(RoutingClass):
    @route()
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
        self.route.plug("logging")

    @route()
    def hello(self):
        return "ok"


def test_router_requires_owner():
    with pytest.raises(ValueError):
        Router(None)  # type: ignore[arg-type]


def test_router_rejects_second_router():
    """Creating a Router on an owner whose router already exists raises."""
    svc = ManualService()
    _ = svc.route  # ensure router exists
    with pytest.raises(ValueError, match="already has a router"):
        Router(svc)


def test_register_plugin_requires_plugin_code():
    class DummyPlugin(BasePlugin):
        pass  # Missing plugin_code

    with pytest.raises(ValueError, match="missing plugin_code"):
        Router.register_plugin(DummyPlugin)


def test_plug_validates_type_and_known_plugin():
    svc = ManualService()
    with pytest.raises(TypeError):
        svc.route.plug(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        svc.route.plug("missing_plugin")


def test_plug_rejects_duplicate_plugin():
    """Plugging the same plugin twice should raise ValueError."""
    svc = ManualService()
    svc.route.plug("logging")
    with pytest.raises(ValueError, match="already attached"):
        svc.route.plug("logging")


def test_add_entry_variants_and_wildcards():
    svc = ManualService()
    svc.route.add_entry(["first", "second"])
    assert "first" in svc.route._entries
    assert "second" in svc.route._entries

    svc.route.add_entry("first, second", replace=True)
    before = set(svc.route._entries.keys())
    assert svc.route.add_entry("   ") is svc.route
    assert set(svc.route._entries.keys()) == before

    with pytest.raises(TypeError):
        svc.route.add_entry(123)

    # Use replace=True since "auto" was already registered by lazy binding
    svc.route.add_entry("*", metadata={"source": "wild"}, replace=True)
    entry = svc.route._entries["auto"]
    assert entry.metadata["marker"] == "yes"
    assert entry.metadata["source"] == "wild"


def test_plugin_on_decore_runs_for_existing_entries():
    svc = ManualService()
    svc.route.plug("stamp_extra")
    svc.route.add_entry(svc.first, name="alias_first")
    assert svc.route._entries["alias_first"].metadata["stamped"] is True


def test_iter_marked_methods_deduplicate_same_function():
    """Test that duplicate markers on same function don't cause double registration."""
    svc = DuplicateMarkers()
    assert svc.route.node("original")() == "ok"
    # Verify only one entry via nodes()
    info = svc.route.nodes()
    assert len(info.get("entries", {})) == 1


def test_mro_override_derived_wins():
    """Test that derived class method overrides base class method (issue #11).

    When a subclass overrides a method decorated with @route, the Router should
    respect Python's MRO and use the overridden method instead of raising
    ValueError: Handler name collision.
    """

    class Base(RoutingClass):
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
    assert d.route.node("index")() == "DERIVED"
    # Verify only one entry registered
    info = d.route.nodes()
    assert len(info.get("entries", {})) == 1


def test_router_node_and_nodes_structure():
    """Test node() and nodes() work correctly."""
    svc = ManualService()
    # auto is marked with @route, so it's available
    assert svc.route.node("auto")() == "auto"
    tree = svc.route.nodes()
    assert tree["entries"]
    assert "routers" not in tree


def test_inherit_plugins_branches():
    parent = ManualService()
    child = ManualService()
    parent.route.plug("stamp_extra")
    before = len(child.route._plugins_by_name)
    child.route._on_attached_to_parent(parent.route)
    after = len(child.route._plugins_by_name)
    assert after > before
    child.route._on_attached_to_parent(parent.route)
    assert len(child.route._plugins_by_name) == after
    # Force missing plugin bucket to exercise seed path
    parent.route._plugin_info.pop("stamp_extra", None)
    child.route._on_attached_to_parent(parent.route)

    orphan = ManualService()
    plain = ManualService()
    plain_before = len(orphan.route._plugins_by_name)
    orphan.route._on_attached_to_parent(plain.route)
    assert len(orphan.route._plugins_by_name) == plain_before


def test_inherit_plugins_seed_from_empty_parent_bucket():
    parent = ManualService()
    parent.route.plug("stamp_extra")
    parent.route._plugin_info.pop("stamp_extra", None)
    child = ManualService()
    child.route._on_attached_to_parent(parent.route)
    # Config is now a callable lookup, verify plugin is accessible
    assert "stamp_extra" in child.route._plugins_by_name


def test_router_nodes_include_metadata_tree():
    parent = ManualService()
    parent.route.add_entry(parent.first)
    info = parent.route.nodes()
    assert "entries" in info


def test_router_nodes_with_basepath():
    """Test nodes() with basepath navigates to child router."""

    class Child(RoutingClass):
        @route()
        def child_action(self):
            return "child"

    class Grandchild(RoutingClass):
        @route()
        def grandchild_action(self):
            return "grandchild"

    class Root(RoutingClass):
        def __init__(self):
            self.child = Child()
            self.child.grandchild = Grandchild()
            self.attach_instance(self.child, name="child")
            self.child.attach_instance(self.child.grandchild, name="grandchild")

        @route()
        def root_action(self):
            return "root"

    root = Root()

    # Without basepath - returns full tree
    full = root.route.nodes()
    assert "root_action" in full["entries"]
    assert "child" in full["routers"]

    # With basepath="child" - returns child subtree
    child_nodes = root.route.nodes(basepath="child")
    assert child_nodes["name"] == "route"
    assert "child_action" in child_nodes["entries"]
    assert "grandchild" in child_nodes["routers"]
    assert "root_action" not in child_nodes.get("entries", {})

    # With basepath="child/grandchild" - returns grandchild subtree
    grandchild_nodes = root.route.nodes(basepath="child/grandchild")
    assert grandchild_nodes["name"] == "route"
    assert "grandchild_action" in grandchild_nodes["entries"]
    assert "routers" not in grandchild_nodes  # no children

    # With basepath pointing to a handler - returns empty dict
    handler_nodes = root.route.nodes(basepath="root_action")
    assert handler_nodes == {}

    # With basepath pointing to non-existent path - returns empty dict
    missing_nodes = root.route.nodes(basepath="nonexistent")
    assert missing_nodes == {}


def test_nodes_lazy_returns_router_references():
    """Test nodes(lazy=True) returns router references for child routers."""

    class Child(RoutingClass):
        @route()
        def child_action(self):
            return "child"

    class Root(RoutingClass):
        def __init__(self):
            self.child = Child()
            self.attach_instance(self.child, name="child")

        @route()
        def root_action(self):
            return "root"

    root = Root()

    # Without lazy - routers dict contains expanded nodes
    full = root.route.nodes()
    assert isinstance(full["routers"]["child"], dict)
    assert "child_action" in full["routers"]["child"]["entries"]

    # With lazy=True - routers dict contains router references (not expanded)
    lazy_nodes = root.route.nodes(lazy=True)
    child_router = lazy_nodes["routers"]["child"]
    assert isinstance(child_router, Router)

    # To expand, call nodes() on the router or use basepath
    child_nodes = child_router.nodes()
    assert isinstance(child_nodes, dict)
    assert "child_action" in child_nodes["entries"]

    # Or use basepath from parent
    child_via_basepath = root.route.nodes(basepath="child")
    assert "child_action" in child_via_basepath["entries"]


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
        svc.routing.configure("/_all_", mode="x")
    with pytest.raises(AttributeError):
        svc.routing.configure("ghost/_all_", flags="on")
    with pytest.raises(ValueError):
        svc.routing.configure("logging/_all_")
    with pytest.raises(KeyError):
        svc.routing.configure("logging/missing*", flags="before")
    result = svc.routing.configure("logging", flags="before")
    assert result["updated"] == ["_all_"]


def test_configure_question_success_and_router_proxy_errors():
    svc = LoggingService()
    description = svc.routing.configure("?")
    assert description["name"] == "route"
    assert "hello" in description["entries"]
    assert any(plugin["name"] == "logging" for plugin in description["plugins"])
    with pytest.raises(KeyError):
        svc.routing.get_router("missing")
    router = svc.routing.get_router()
    assert router is svc.route


def test_get_router_skips_empty_segments():
    class Leaf(RoutingClass):
        pass

    class Parent(RoutingClass):
        def __init__(self):
            self.child = Leaf()
            self.route._children["child"] = self.child.route  # direct attach for test

    svc = Parent()
    router = svc.routing.get_router("child//")
    assert router is svc.child.route


def test_is_routing_class_helper():
    svc = ManualService()
    assert is_routing_class(svc) is True
    assert is_routing_class(object()) is False


def test_nodes_includes_description_and_owner_doc():
    """Test nodes() includes router description and owner docstring."""

    class ArticleService(RoutingClass):
        """Service for managing articles."""

        def __init__(self):
            self.route.description = "API for articles"

        @route()
        def list_articles(self):
            return []

    svc = ArticleService()
    nodes = svc.route.nodes()

    assert nodes["description"] == "API for articles"
    assert nodes["owner_doc"] == "Service for managing articles."


def test_nodes_description_none_when_not_set():
    """Test nodes() returns None for description when not set."""

    class SimpleService(RoutingClass):
        @route()
        def action(self):
            pass

    svc = SimpleService()
    nodes = svc.route.nodes()

    assert nodes["description"] is None
    assert nodes["owner_doc"] is None  # No docstring on class


# -----------------------------------------------------------------------------
# node() method tests
# -----------------------------------------------------------------------------


def test_node_returns_entry_info():
    """Test node() returns RouterNode for a single entry."""

    class Svc(RoutingClass):
        @route()
        def get_item(self, item_id: int) -> dict:
            """Get an item by ID."""
            return {"id": item_id}

    svc = Svc()
    node = svc.route.node("get_item")

    assert node.path == "get_item"
    assert node.doc == "Get an item by ID."
    assert node.metadata is not None


# -----------------------------------------------------------------------
# Response schema in pydantic metadata
# -----------------------------------------------------------------------


def test_pydantic_captures_response_schema():
    """Pydantic plugin captures response schema from return type annotation."""

    class Svc(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def get_data(self) -> dict[str, int]:
            """Return data."""
            return {"a": 1}

    svc = Svc()
    entry = svc.route._entries["get_data"]
    meta = entry.metadata.get("pydantic", {})
    assert "response_schema" in meta
    schema = meta["response_schema"]
    assert schema["type"] == "object"


def test_pydantic_no_response_schema_without_annotation():
    """No response_schema when handler has no return annotation."""

    class Svc(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def no_return(self):
            return {}

    svc = Svc()
    entry = svc.route._entries["no_return"]
    meta = entry.metadata.get("pydantic", {})
    assert "response_schema" not in meta


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="TypedDict type hints not resolved by pydantic on Python <3.12",
)
def test_pydantic_captures_typeddict_response_schema():
    """Pydantic plugin generates correct schema for TypedDict return type."""

    class Svc(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def get_user(self) -> _UserResponse:
            return {"id": 1, "name": "test", "active": True}

    svc = Svc()
    entry = svc.route._entries["get_user"]
    schema = entry.metadata["pydantic"]["response_schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert schema["properties"]["id"]["type"] == "integer"
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["active"]["type"] == "boolean"


def test_response_schema_in_nodes_metadata():
    """nodes() exposes response_schema in pydantic plugin metadata."""

    class Svc(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def get_data(self) -> dict[str, int]:
            """Return data."""
            return {"a": 1}

    svc = Svc()
    nodes = svc.route.nodes()
    entry_info = nodes["entries"]["get_data"]
    pydantic_meta = entry_info["plugins"]["pydantic"]["metadata"]
    assert "response_schema" in pydantic_meta
    assert pydantic_meta["response_schema"]["type"] == "object"


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="TypedDict type hints not resolved by pydantic on Python <3.12",
)
def test_list_typeddict_response_schema():
    """Pydantic plugin handles list[TypedDict] return type."""

    class Svc(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def list_users(self) -> list[_UserResponse]:
            return []

    svc = Svc()
    entry = svc.route._entries["list_users"]
    schema = entry.metadata["pydantic"]["response_schema"]
    assert schema["type"] == "array"
