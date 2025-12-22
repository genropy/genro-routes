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

"""Tests for instance-based Router core functionality."""

import pytest

from genro_routes import RoutingClass, Router, route
from genro_routes.plugins._base_plugin import BasePlugin  # Not public API


def test_orders_quick_example():
    class OrdersAPI(RoutingClass):
        def __init__(self, label: str):
            self.label = label
            self.api = Router(self, name="orders")

        @route("orders")
        def list(self):
            return ["order-1", "order-2"]

        @route("orders")
        def retrieve(self, ident: str):
            return f"{self.label}:{ident}"

        @route("orders")
        def create(self, payload: dict):
            return {"status": "created", **payload}

    orders = OrdersAPI("acme")
    # Use node() and call it
    assert orders.api.node("list")() == ["order-1", "order-2"]
    assert orders.api.node("retrieve")("42") == "acme:42"
    overview = orders.api.nodes()
    assert set(overview["entries"].keys()) == {"list", "retrieve", "create"}


class Service(RoutingClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="api")

    @route("api")
    def describe(self):
        return f"service:{self.label}"


class SubService(RoutingClass):
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.routes = Router(self, name="routes", prefix="handle_")

    @route("routes")
    def handle_list(self):
        return f"{self.prefix}:list"

    @route("routes", name="detail")
    def handle_detail(self, ident: int):
        return f"{self.prefix}:detail:{ident}"


class RootAPI(RoutingClass):
    def __init__(self):
        self.services: list[Service] = []
        self.api = Router(self, name="api")


class CapturePlugin(BasePlugin):
    plugin_code = "capture"
    plugin_description = "Captures calls for testing"

    def __init__(self, router, **config):
        super().__init__(router, **config)
        self.calls = []

    def on_decore(self, route, func, entry):
        entry.metadata["capture"] = True

    def wrap_handler(self, route, entry, call_next):
        def wrapper(*args, **kwargs):
            self.calls.append("wrap")
            return call_next(*args, **kwargs)

        return wrapper


# Register custom plugin
Router.register_plugin(CapturePlugin)


class PluginService(RoutingClass):
    def __init__(self):
        self.touched = False
        self.api = Router(self, name="api").plug("capture")

    @route("api")
    def do_work(self):
        self.touched = True
        return "ok"


class TogglePlugin(BasePlugin):
    plugin_code = "toggle"
    plugin_description = "Toggle test plugin"

    def __init__(self, router, **config):
        super().__init__(router, **config)

    def wrap_handler(self, route, entry, call_next):
        def wrapper(*args, **kwargs):
            route.set_runtime_data(entry.name, self.name, "last", True)
            return call_next(*args, **kwargs)

        return wrapper


# Register custom plugin
Router.register_plugin(TogglePlugin)


class ToggleService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api").plug("toggle")

    @route("api")
    def touch(self):
        return "done"


class DynamicRouterService(RoutingClass):
    def __init__(self):
        self.dynamic = Router(self, name="dynamic")
        self.dynamic._add_entry(self.dynamic_alpha)
        self.dynamic._add_entry("dynamic_beta")

    def dynamic_alpha(self):
        return "alpha"

    def dynamic_beta(self):
        return "beta"


def test_instance_bound_methods_are_isolated():
    first = Service("alpha")
    second = Service("beta")

    assert first.api.node("describe")() == "service:alpha"
    assert second.api.node("describe")() == "service:beta"
    # Ensure handlers are distinct objects (bound to each instance)
    assert first.api.node("describe").callable != second.api.node("describe").callable


def test_prefix_and_name_override():
    sub = SubService("users")

    assert sub.routes.node("list")() == "users:list"
    assert sub.routes.node("detail")(10) == "users:detail:10"


def test_plugins_are_per_instance_and_accessible():
    svc = PluginService()
    assert svc.api.capture.calls == []
    result = svc.api.node("do_work")()
    assert result == "ok"
    assert svc.touched is True
    assert svc.api.capture.calls == ["wrap"]
    other = PluginService()
    assert other.api.capture.calls == []


def test_dynamic_router_add_entry_runtime():
    svc = DynamicRouterService()
    assert svc.dynamic.node("dynamic_alpha")() == "alpha"
    assert svc.dynamic.node("dynamic_beta")() == "beta"
    # Adding via string
    svc.dynamic._add_entry("dynamic_alpha", name="alpha_alias")
    assert svc.dynamic.node("alpha_alias")() == "alpha"


def test_plugin_enable_disable_runtime_data():
    svc = ToggleService()
    node = svc.api.node("touch")
    # Initially enabled
    node()
    assert svc.api.get_runtime_data("touch", "toggle", "last") is True
    # Disable and verify
    svc.api.set_plugin_enabled("touch", "toggle", False)
    svc.api.set_runtime_data("touch", "toggle", "last", None)
    node()
    assert svc.api.get_runtime_data("touch", "toggle", "last") is None
    # Re-enable
    svc.api.set_plugin_enabled("touch", "toggle", True)
    node()
    assert svc.api.get_runtime_data("touch", "toggle", "last") is True


def test_dotted_path_and_nodes_with_attached_child():
    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def ping(self):
            return "pong"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

    parent = Parent()
    assert parent.api.node("child/ping")() == "pong"
    tree = parent.api.nodes()
    assert "child" in tree["routers"]


# ============================================================================
# main_router class attribute tests
# ============================================================================


class TestMainRouterAttribute:
    """Test @route() with main_router class attribute."""

    def test_route_without_args_uses_main_router(self):
        """@route() without arguments uses main_router class attribute."""

        class Table(RoutingClass):
            main_router = "table"

            def __init__(self):
                self.api = Router(self, name="table")

            @route()
            def add(self, data):
                return f"added:{data}"

            @route()
            def get(self, key):
                return f"got:{key}"

        t = Table()
        assert t.api.node("add")("x") == "added:x"
        assert t.api.node("get")("y") == "got:y"
        assert set(t.api.nodes()["entries"].keys()) == {"add", "get"}

    def test_route_with_explicit_name_overrides_main_router(self):
        """@route('other') ignores main_router."""

        class Mixed(RoutingClass):
            main_router = "api"

            def __init__(self):
                self.api = Router(self, name="api")
                self.admin = Router(self, name="admin")

            @route()  # Uses main_router = "api"
            def public(self):
                return "public"

            @route("admin")  # Explicit, ignores main_router
            def secret(self):
                return "secret"

        m = Mixed()
        assert m.api.node("public")() == "public"
        assert m.admin.node("secret")() == "secret"
        assert "public" in m.api.nodes()["entries"]
        assert "secret" not in m.api.nodes()["entries"]
        assert "secret" in m.admin.nodes()["entries"]

    def test_route_without_main_router_is_ignored(self):
        """@route() without main_router is not registered anywhere."""

        class NoDefault(RoutingClass):
            # No main_router defined

            def __init__(self):
                self.api = Router(self, name="api")

            @route()  # No router specified, no main_router - ignored
            def orphan(self):
                return "orphan"

            @route("api")
            def registered(self):
                return "registered"

        nd = NoDefault()
        assert nd.api.node("registered")() == "registered"
        # orphan not registered - node returns empty
        assert not nd.api.node("orphan")
        assert "orphan" not in nd.api.nodes()["entries"]

    def test_main_router_with_custom_entry_name(self):
        """@route(name='custom') works with main_router."""

        class Table(RoutingClass):
            main_router = "table"

            def __init__(self):
                self.api = Router(self, name="table")

            @route(name="custom_add")
            def add_record(self, data):
                return f"added:{data}"

        t = Table()
        assert t.api.node("custom_add")("x") == "added:x"
        assert "custom_add" in t.api.nodes()["entries"]
        assert "add_record" not in t.api.nodes()["entries"]

    def test_main_router_inheritance(self):
        """Subclass inherits main_router from parent."""

        class BaseTable(RoutingClass):
            main_router = "table"

            @route()
            def list(self):
                return "base_list"

        class ExtendedTable(BaseTable):
            def __init__(self):
                self.api = Router(self, name="table")

            @route()
            def add(self):
                return "extended_add"

        t = ExtendedTable()
        assert t.api.node("list")() == "base_list"
        assert t.api.node("add")() == "extended_add"
        entries = t.api.nodes()["entries"]
        assert "list" in entries
        assert "add" in entries

    def test_main_router_override_in_subclass(self):
        """Subclass can override main_router - affects all methods including inherited."""

        class BaseTable(RoutingClass):
            main_router = "table"

            @route()
            def base_method(self):
                return "base"

        class ChildTable(BaseTable):
            main_router = "custom"  # Override - affects ALL @route() including inherited

            def __init__(self):
                self.custom = Router(self, name="custom")

            @route()
            def child_method(self):
                return "child"

        t = ChildTable()
        # Both methods use ChildTable's main_router = "custom"
        # because main_router is resolved at registration time from instance's class
        assert t.custom.node("base_method")() == "base"
        assert t.custom.node("child_method")() == "child"
        entries = t.custom.nodes()["entries"]
        assert "base_method" in entries
        assert "child_method" in entries

    def test_main_router_with_plugin_kwargs(self):
        """@route() with kwargs works with main_router."""

        class TaggedTable(RoutingClass):
            main_router = "table"

            def __init__(self):
                self.api = Router(self, name="table").plug("auth")

            @route(auth_tags="admin")
            def admin_only(self):
                return "admin"

            @route(auth_tags="public")
            def public_action(self):
                return "public"

        t = TaggedTable()
        entries = t.api.nodes(auth_tags="admin")["entries"]
        assert "admin_only" in entries
        assert "public_action" not in entries


# ============================================================================
# RoutingClass requirement and default_router tests
# ============================================================================


class TestRoutingClassRequirement:
    """Test that Router requires RoutingClass."""

    def test_router_requires_routed_class(self):
        """Router raises TypeError if owner is not a RoutingClass."""

        class PlainClass:
            pass

        with pytest.raises(TypeError, match="must be a RoutingClass"):
            Router(PlainClass(), name="api")

    def test_router_accepts_routed_class(self):
        """Router accepts RoutingClass instances."""

        class MyService(RoutingClass):
            pass

        svc = MyService()
        router = Router(svc, name="api")
        assert router.instance is svc


class TestDefaultRouter:
    """Test default_router property on RoutingClass."""

    def test_default_router_single_router(self):
        """default_router returns the only router when there's exactly one."""

        class SingleRouter(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = SingleRouter()
        assert svc.default_router is svc.api

    def test_default_router_multiple_routers_no_main(self):
        """default_router returns None when multiple routers and no main_router."""

        class MultiRouter(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.admin = Router(self, name="admin")

        svc = MultiRouter()
        assert svc.default_router is None

    def test_default_router_uses_main_router_attribute(self):
        """default_router respects main_router class attribute."""

        class WithMainRouter(RoutingClass):
            main_router = "admin"

            def __init__(self):
                self.api = Router(self, name="api")
                self.admin = Router(self, name="admin")

        svc = WithMainRouter()
        assert svc.default_router is svc.admin

    def test_default_router_no_routers(self):
        """default_router returns None when no routers registered."""

        class NoRouters(RoutingClass):
            pass

        svc = NoRouters()
        assert svc.default_router is None

    def test_default_router_main_router_not_found(self):
        """default_router returns None when main_router name doesn't match any router."""

        class BadMainRouter(RoutingClass):
            main_router = "nonexistent"

            def __init__(self):
                self.api = Router(self, name="api")

        svc = BadMainRouter()
        assert svc.default_router is None


# -----------------------------------------------------------------------------
# Tests for default_entry behavior with node()
# -----------------------------------------------------------------------------


class TestDefaultEntry:
    """Tests for Router.default_entry behavior with node()."""

    def test_default_entry_is_index_by_default(self):
        """Router default_entry is 'index' by default."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self):
                return "action"

        svc = Service()
        assert svc.api.default_entry == "index"

    def test_default_entry_can_be_customized(self):
        """Router default_entry can be set to a custom value."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api", default_entry="handle")

            @route("api")
            def handle(self):
                return "handle"

        svc = Service()
        assert svc.api.default_entry == "handle"

    def test_node_uses_default_entry_for_unresolved_path(self):
        """node() uses default_entry for paths that don't resolve exactly."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def index(self, *args):
                return f"index called with {args}"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        # Path "child/extra/path" - child exists but "extra/path" doesn't
        # Should return node with default_entry ("index") and extra_args
        node = root.api.node("child/extra/path")

        assert node
        assert node.default_entry is True
        assert node.extra_args == ["extra", "path"]
        assert node.partial_kwargs == {}
        # extra_args are automatically prepended when calling the node
        assert node() == "index called with ('extra', 'path')"

    def test_node_uses_custom_default_entry(self):
        """node() uses custom default_entry when configured."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api", default_entry="handle")

            @route("api")
            def handle(self, *args):
                return f"handle called with {args}"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        node = root.api.node("child/extra/path")

        assert node
        assert node.default_entry is True
        assert node.extra_args == ["extra", "path"]
        assert node.partial_kwargs == {}
        # extra_args are automatically prepended when calling the node
        assert node() == "handle called with ('extra', 'path')"

    def test_node_returns_empty_when_default_entry_missing(self):
        """node() returns empty RouterNode when default_entry doesn't exist."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")  # default_entry="index" but no index entry

            @route("api")
            def action(self):  # Not named "index"
                return "action"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        node = root.api.node("child/extra/path")

        # No default_entry available, returns empty node
        assert not node
        assert node == {}

    def test_leading_slash_is_stripped(self):
        """node() strips leading slash from path."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self):
                return "action result"

        svc = Service()

        # Both should work identically
        assert svc.api.node("action")() == "action result"
        assert svc.api.node("/action")() == "action result"

    def test_leading_slash_with_hierarchy(self):
        """node() strips leading slash in hierarchical paths."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def handler(self):
                return "child handler"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()

        # Both should work identically
        assert root.api.node("child/handler")() == "child handler"
        assert root.api.node("/child/handler")() == "child handler"
