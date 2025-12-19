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

import sys

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
    assert orders.api.get("list")() == ["order-1", "order-2"]
    assert orders.api.get("retrieve")("42") == "acme:42"
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

    assert first.api.get("describe")() == "service:alpha"
    assert second.api.get("describe")() == "service:beta"
    # Ensure handlers are distinct objects (bound to each instance)
    assert first.api.get("describe") != second.api.get("describe")


def test_prefix_and_name_override():
    sub = SubService("users")

    assert sub.routes.get("list")() == "users:list"
    assert sub.routes.get("detail")(10) == "users:detail:10"


def test_plugins_are_per_instance_and_accessible():
    svc = PluginService()
    assert svc.api.capture.calls == []
    result = svc.api.get("do_work")()
    assert result == "ok"
    assert svc.touched is True
    assert svc.api.capture.calls == ["wrap"]
    other = PluginService()
    assert other.api.capture.calls == []


def test_dynamic_router_add_entry_runtime():
    svc = DynamicRouterService()
    assert svc.dynamic.get("dynamic_alpha")() == "alpha"
    assert svc.dynamic.get("dynamic_beta")() == "beta"
    # Adding via string
    svc.dynamic._add_entry("dynamic_alpha", name="alpha_alias")
    assert svc.dynamic.get("alpha_alias")() == "alpha"


def test_get_with_default_returns_callable():
    svc = PluginService()

    def fallback():
        return "fallback"

    handler = svc.api.get("missing", default_handler=fallback)
    assert handler() == "fallback"


def test_get_with_smartasync(monkeypatch):
    calls = []

    def fake_smartasync(fn):
        def wrapper(*a, **k):
            calls.append("wrapped")
            return fn(*a, **k)

        return wrapper

    fake_module = type(sys)("smartasync")
    fake_module.smartasync = fake_smartasync
    monkeypatch.setitem(sys.modules, "smartasync", fake_module)
    svc = PluginService()
    handler = svc.api.get("do_work", use_smartasync=True)
    handler()
    assert calls == ["wrapped"]


def test_get_uses_init_default_handler():
    class DefaultService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api", get_default_handler=lambda: "init-default")

    svc = DefaultService()
    handler = svc.api.get("missing")
    assert handler() == "init-default"


def test_get_runtime_override_init_default_handler():
    class DefaultService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api", get_default_handler=lambda: "init-default")

    svc = DefaultService()
    handler = svc.api.get("missing", default_handler=lambda: "runtime")
    assert handler() == "runtime"


def test_get_without_default_returns_none():
    svc = PluginService()
    result = svc.api.get("unknown")
    assert result is None


def test_get_uses_init_smartasync(monkeypatch):
    calls = []

    def fake_smartasync(fn):
        def wrapper(*args, **kwargs):
            calls.append("wrapped")
            return fn(*args, **kwargs)

        return wrapper

    fake_module = type(sys)("smartasync")
    fake_module.smartasync = fake_smartasync
    monkeypatch.setitem(sys.modules, "smartasync", fake_module)

    class AsyncService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api", get_use_smartasync=True)

        @route("api")
        def do_work(self):
            return "ok"

    svc = AsyncService()
    handler = svc.api.get("do_work")
    assert handler() == "ok"
    assert calls == ["wrapped"]


def test_get_can_disable_init_smartasync(monkeypatch):
    calls = []

    def fake_smartasync(fn):
        def wrapper(*args, **kwargs):
            calls.append("wrapped")
            return fn(*args, **kwargs)

        return wrapper

    fake_module = type(sys)("smartasync")
    fake_module.smartasync = fake_smartasync
    monkeypatch.setitem(sys.modules, "smartasync", fake_module)

    class AsyncService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api", get_use_smartasync=True)

        @route("api")
        def do_work(self):
            return "ok"

    svc = AsyncService()
    handler = svc.api.get("do_work", use_smartasync=False)
    assert handler() == "ok"
    assert calls == []


def test_plugin_enable_disable_runtime_data():
    svc = ToggleService()
    handler = svc.api.get("touch")
    # Initially enabled
    handler()
    assert svc.api.get_runtime_data("touch", "toggle", "last") is True
    # Disable and verify
    svc.api.set_plugin_enabled("touch", "toggle", False)
    svc.api.set_runtime_data("touch", "toggle", "last", None)
    handler()
    assert svc.api.get_runtime_data("touch", "toggle", "last") is None
    # Re-enable
    svc.api.set_plugin_enabled("touch", "toggle", True)
    handler()
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
    assert parent.api.get("child/ping")() == "pong"
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
        assert t.api.get("add")("x") == "added:x"
        assert t.api.get("get")("y") == "got:y"
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
        assert m.api.get("public")() == "public"
        assert m.admin.get("secret")() == "secret"
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
        assert nd.api.get("registered")() == "registered"
        assert nd.api.get("orphan") is None
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
        assert t.api.get("custom_add")("x") == "added:x"
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
        assert t.api.get("list")() == "base_list"
        assert t.api.get("add")() == "extended_add"
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
        assert t.custom.get("base_method")() == "base"
        assert t.custom.get("child_method")() == "child"
        entries = t.custom.nodes()["entries"]
        assert "base_method" in entries
        assert "child_method" in entries

    def test_main_router_with_plugin_kwargs(self):
        """@route() with kwargs works with main_router."""

        class TaggedTable(RoutingClass):
            main_router = "table"

            def __init__(self):
                self.api = Router(self, name="table").plug("filter")

            @route(filter_tags="admin")
            def admin_only(self):
                return "admin"

            @route(filter_tags="public")
            def public_action(self):
                return "public"

        t = TaggedTable()
        entries = t.api.nodes(tags="admin")["entries"]
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
# get() with partial=True tests
# -----------------------------------------------------------------------------


class TestGetWithPartial:
    """Tests for get() with partial=True option."""

    def test_partial_returns_functools_partial_for_unresolved_path(self):
        """get(partial=True) returns partial with default_entry handler for unresolved paths."""
        import functools

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def index(self, *args):
                return f"index called with: {args}"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        # "child" exists, but "gamma/delta" doesn't
        # Should use child's default_entry ("index") with unconsumed path as args
        result = root.api.get("child/gamma/delta", partial=True)

        assert isinstance(result, functools.partial)
        # The partial should call the index handler with path segments as args
        output = result()
        assert output == "index called with: ('gamma', 'delta')"

    def test_partial_can_be_called_later(self):
        """partial result can be invoked later with bound args."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def catch_all(self, *args):
                return list(args)

        svc = Service()
        # "catch_all" exists, "extra/path" doesn't - should return partial on catch_all
        result = svc.api.get("catch_all/extra/path", partial=True)

        # Call the partial - args are already bound
        output = result()
        assert output == ["extra", "path"]

    def test_partial_with_nested_hierarchy(self):
        """partial works correctly with deeply nested router hierarchies."""
        import functools

        class GrandChild(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def index(self, *args):
                return f"grandchild index: {args}"

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.grandchild = GrandChild()
                self.api.attach_instance(self.grandchild, name="grandchild")

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        # Path "child/grandchild" exists, but "nonexistent/path" doesn't
        # Should use grandchild's default_entry ("index") with unconsumed path as args
        result = root.api.get("child/grandchild/nonexistent/path", partial=True)

        assert isinstance(result, functools.partial)
        # Call the partial and verify result
        output = result()
        assert output == "grandchild index: ('nonexistent', 'path')"

    def test_partial_false_returns_none_for_unresolved(self):
        """Without partial=True, get() returns None for unresolved paths."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self):
                return "ok"

        svc = Service()
        # Default behavior - no partial
        result = svc.api.get("nonexistent/path")
        assert result is None

        # Explicit partial=False
        result = svc.api.get("nonexistent/path", partial=False)
        assert result is None

    def test_partial_with_single_segment_unresolved_returns_none(self):
        """partial=True returns None for non-existent single segment (no router to resolve)."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self):
                return "ok"

        svc = Service()
        # Single segment that doesn't exist - no router to get default_entry from
        result = svc.api.get("nonexistent", partial=True)
        assert result is None

    def test_partial_resolved_path_returns_normal_result(self):
        """When path is fully resolved, partial=True doesn't change behavior."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self, x=None):
                return f"x={x}"

        svc = Service()
        # Path exists - should return the handler directly
        result = svc.api.get("action", partial=True)

        # Should be the actual handler, not a partial
        assert callable(result)
        assert result(x=42) == "x=42"

    def test_partial_entry_with_extra_path_segments(self):
        """When entry exists but has extra path, return partial with segments as args."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def handler(self, *args):
                return list(args)

        svc = Service()
        # "handler" exists, "extra/segments" are unconsumed
        result = svc.api.get("handler/extra/segments", partial=True)

        # Should be partial with extra segments as args
        output = result()
        assert output == ["extra", "segments"]


# -----------------------------------------------------------------------------
# Tests for default_entry with partial
# -----------------------------------------------------------------------------


class TestDefaultEntryWithPartial:
    """Tests for Router.default_entry behavior with partial=True."""

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

    def test_partial_uses_default_entry_on_child_router(self):
        """partial=True uses child router's default_entry (index) for unresolved path."""
        import functools

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
        # Should return partial(child.api.index, "extra", "path")
        result = root.api.get("child/extra/path", partial=True)

        assert isinstance(result, functools.partial)
        output = result()
        assert output == "index called with ('extra', 'path')"

    def test_partial_uses_custom_default_entry(self):
        """partial=True uses custom default_entry when configured."""
        import functools

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
        result = root.api.get("child/extra/path", partial=True)

        assert isinstance(result, functools.partial)
        output = result()
        assert output == "handle called with ('extra', 'path')"

    def test_partial_raises_when_default_entry_missing(self):
        """partial=True raises ValueError when default_entry doesn't exist."""
        import pytest

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

        with pytest.raises(ValueError, match="No default entry 'index'"):
            root.api.get("child/extra/path", partial=True)

    def test_partial_on_router_single_segment_uses_default_entry(self):
        """partial=True on single segment router uses default_entry."""
        import functools

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def index(self):
                return "index"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        # Just "child" - resolves to router, partial=True should use default_entry
        result = root.api.get("child", partial=True)

        assert isinstance(result, functools.partial)
        assert result() == "index"

    def test_partial_false_returns_router_not_default_entry(self):
        """Without partial=True, get() returns the router itself."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def index(self):
                return "index"

        class Root(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Root()
        result = root.api.get("child")

        # Without partial=True, returns the router itself
        assert result is root.child.api

    def test_partial_empty_selector_uses_default_entry(self):
        """partial=True with empty selector uses this router's default_entry."""
        import functools

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def index(self):
                return "index called"

        svc = Service()
        result = svc.api.get("", partial=True)

        assert isinstance(result, functools.partial)
        assert result() == "index called"

    def test_partial_empty_selector_raises_when_default_entry_missing(self):
        """partial=True with empty selector raises when default_entry missing."""
        import pytest

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self):  # Not "index"
                return "action"

        svc = Service()

        with pytest.raises(ValueError, match="No default entry 'index'.*empty partial path"):
            svc.api.get("", partial=True)

    def test_leading_slash_is_stripped(self):
        """get() strips leading slash from selector."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def action(self):
                return "action result"

        svc = Service()

        # Both should work identically
        assert svc.api.get("action")() == "action result"
        assert svc.api.get("/action")() == "action result"

    def test_leading_slash_with_hierarchy(self):
        """get() strips leading slash in hierarchical paths."""

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
        assert root.api.get("child/handler")() == "child handler"
        assert root.api.get("/child/handler")() == "child handler"
