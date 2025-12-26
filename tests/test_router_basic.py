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
        self.dynamic.add_entry(self.dynamic_alpha)
        self.dynamic.add_entry("dynamic_beta")

    def dynamic_alpha(self):
        return "alpha"

    def dynamic_beta(self):
        return "beta"


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
    svc.dynamic.add_entry("dynamic_alpha", name="alpha_alias")
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
# Single router default tests (@route() without arguments)
# ============================================================================


class TestSingleRouterDefault:
    """Test @route() without arguments when class has a single router."""

    def test_route_without_args_uses_single_router(self):
        """@route() without arguments uses the single router."""

        class Table(RoutingClass):
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

    def test_route_with_custom_entry_name(self):
        """@route(name='custom') works with single router."""

        class Table(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="table")

            @route(name="custom_add")
            def add_record(self, data):
                return f"added:{data}"

        t = Table()
        assert t.api.node("custom_add")("x") == "added:x"
        assert "custom_add" in t.api.nodes()["entries"]
        assert "add_record" not in t.api.nodes()["entries"]

    def test_route_inheritance_with_single_router(self):
        """Subclass with single router inherits @route() methods."""

        class BaseTable(RoutingClass):
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

    def test_route_with_plugin_kwargs(self):
        """@route() with kwargs works with single router."""

        class TaggedTable(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="table").plug("auth")

            @route(auth_rule="admin")
            def admin_only(self):
                return "admin"

            @route(auth_rule="public")
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

    def test_default_router_multiple_routers(self):
        """default_router returns None when multiple routers exist."""

        class MultiRouter(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.admin = Router(self, name="admin")

        svc = MultiRouter()
        assert svc.default_router is None

    def test_default_router_no_routers(self):
        """default_router returns None when no routers registered."""

        class NoRouters(RoutingClass):
            pass

        svc = NoRouters()
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
