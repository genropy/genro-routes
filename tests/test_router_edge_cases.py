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

"""Tests for Router edge cases and plugin behavior."""

import pytest

from genro_routes import Router, RoutingClass, Section, route
from genro_routes.plugins import pydantic as pyd_mod
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry  # Not public API


class SimplePlugin(BasePlugin):
    plugin_code = "simple"
    plugin_description = "Simple test plugin"

    def configure(self, **config):
        """Accept any configuration - storage is handled by wrapper."""
        pass  # Storage is handled by the wrapper

    def wrap_handler(self, router, entry, call_next):
        return call_next


def test_plugin_configure_and_configuration():
    class Host(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

    svc = Host()
    # Access plugin via public attribute
    plugin = svc.route.simple

    # Test configure() with flags
    plugin.configure(flags="enabled,,beta")
    assert svc.route.get_config("simple")["enabled"] is True
    plugin.configure(threshold=5)
    assert svc.route.get_config("simple")["threshold"] == 5
    # Test configuration() reads back
    assert plugin.configuration()["threshold"] == 5

    # Test per-handler config with _target
    plugin.configure(_target="foo", flags="enabled:off")
    assert svc.route.get_config("simple", "foo")["enabled"] is False
    plugin.configure(_target="foo", mode="strict")
    assert svc.route.get_config("simple", "foo")["mode"] == "strict"


def test_plugin_constructor_flags():
    class Host(RoutingClass):
        def __init__(self):
            self.route.plug("simple", flags="beta:on,alpha:off")

    svc = Host()
    # Access plugin via public attribute
    plugin = svc.route.simple
    assert svc.route.get_config("simple")["beta"] is True
    assert svc.route.get_config("simple")["alpha"] is False
    # Per-handler config via configure()
    plugin.configure(_target="foo", enabled=False)
    assert svc.route.get_config("simple", "foo")["enabled"] is False


def ensure_plugin(plugin_cls: type) -> None:
    if plugin_cls.plugin_code not in Router.available_plugins():
        Router.register_plugin(plugin_cls)


ensure_plugin(SimplePlugin)


def test_plugin_configuration_has_defaults():
    """Test that plugin configuration returns default config when no custom config set."""

    class Host(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

    svc = Host()
    # Fresh plugin has default enabled=True
    assert svc.route.simple.configuration()["enabled"] is True


def test_plugin_missing_plugin_raises():
    """Test that accessing missing plugin raises AttributeError."""

    class Host(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

    svc = Host()
    # Missing plugin triggers AttributeError on public setters/getters
    with pytest.raises(AttributeError):
        svc.route.set_plugin_enabled("foo", "ghost", True)
    with pytest.raises(AttributeError):
        svc.route.get_runtime_data("foo", "ghost", "k")
    with pytest.raises(AttributeError):
        svc.route.set_runtime_data("foo", "ghost", "k", 1)
    with pytest.raises(AttributeError):
        svc.route.is_plugin_enabled("foo", "ghost")


def test_route_decorator_with_plugin_options():
    """Test that handlers with plugin options in decorator work correctly."""

    class Host(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

        @route(simple_flag=True, simple_mode="x")
        def run(self):
            return "ok"

    svc = Host()
    # Handler works and is registered
    assert svc.route.node("run")() == "ok"
    # Entry is registered in nodes()
    info = svc.route.nodes()
    assert "run" in info["entries"]


def test_plugin_configure_after_binding():
    """Test that configure() works after binding."""

    class Host(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

        @route()
        def hello(self):
            return "hi"

    svc = Host()
    # Apply options via configure() after binding
    svc.route.simple.configure(opt="via_configure")
    # Options from configure() call are accessible via get_config()
    assert svc.route.get_config("simple")["opt"] == "via_configure"
    # Handler still works
    assert svc.route.node("hello")() == "hi"


def test_route_decorator_metadata_preserved():
    """Test that custom metadata from route decorator is preserved."""

    class Host(RoutingClass):
        @route(core_value=123)
        def hello(self):
            return "hi"

    svc = Host()
    # Verify handler works
    assert svc.route.node("hello")() == "hi"
    # Verify entry is registered
    info = svc.route.nodes()
    assert "hello" in info["entries"]


def test_router_auto_registers_marked_methods_and_validates_plugins():
    class Demo(RoutingClass):
        @route(name="alias")
        def handle(self):
            return "ok"

    svc = Demo()
    assert svc.route.node("alias")() == "ok"
    ensure_plugin(SimplePlugin)
    svc.route.plug("simple")
    with pytest.raises(ValueError):
        svc.route.plug("missing")


def test_router_detects_handler_name_collision():
    class DuplicateService(RoutingClass):
        @route(name="dup")
        def first(self):
            return "one"

        @route(name="dup")
        def second(self):
            return "two"

    svc = DuplicateService()
    with pytest.raises(ValueError):
        svc.route.nodes()  # Lazy binding triggers collision error


def test_iter_plugins_and_missing_attribute():
    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

        @route()
        def ping(self):
            return "pong"

    svc = Service()
    plugins = svc.route.iter_plugins()
    assert plugins and isinstance(plugins[0], SimplePlugin)
    with pytest.raises(AttributeError):
        _ = svc.route.missing_plugin  # type: ignore[attr-defined]


def test_attach_and_detach_instance_single_router_with_alias():
    class Child(RoutingClass):
        @route()
        def ping(self):
            return "pong"

    class Parent(RoutingClass):
        def __init__(self):
            self.child = Child()

    parent = Parent()
    parent.attach_instance(parent.child, name="sales")
    # Verify child is accessible via nodes()
    info = parent.route.nodes()
    assert "sales" in info.get("routers", {})
    # Verify handler is accessible via path
    assert parent.route.node("sales/ping")() == "pong"

    parent.route.detach_instance(parent.child)
    # Verify child is no longer accessible
    info = parent.route.nodes()
    assert "sales" not in info.get("routers", {})


def test_attach_instance_name_collision():
    class Child(RoutingClass):
        pass

    class Parent(RoutingClass):
        def __init__(self):
            self.child1 = Child()
            self.child2 = Child()

    parent = Parent()
    parent.attach_instance(parent.child1, name="sales")
    with pytest.raises(ValueError):
        parent.attach_instance(parent.child2, name="sales")


def test_detach_instance_removes_all_aliases():
    """detach_instance removes every alias pointing to the child instance."""

    class Child(RoutingClass):
        @route()
        def ping(self):
            return "pong"

    class Parent(RoutingClass):
        pass

    parent = Parent()
    child = Child()
    parent.attach_instance(child, name="first")
    # Secondary navigation link to the same child router
    parent.route.include(child.route, name="second")
    info = parent.route.nodes()
    assert "first" in info.get("routers", {})
    assert "second" in info.get("routers", {})
    # detach removes both aliases
    parent.route.detach_instance(child)
    info = parent.route.nodes()
    assert info.get("routers", {}) == {}


def test_attach_instance_requires_routing_class():
    class Parent(RoutingClass):
        pass

    parent = Parent()
    with pytest.raises(TypeError):
        parent.attach_instance(object(), name="x")
    with pytest.raises(TypeError):
        parent.route.detach_instance(object())


def test_auto_detach_on_attribute_replacement():
    class Child(RoutingClass):
        @route()
        def ping(self):
            return "pong"

    class Parent(RoutingClass):
        def __init__(self):
            self.child = Child()
            self.attach_instance(self.child, name="child")

    parent = Parent()
    # Verify child is attached via nodes()
    info = parent.route.nodes()
    assert "child" in info.get("routers", {})
    # Verify handler is accessible
    assert parent.route.node("child/ping")() == "pong"

    parent.child = None  # triggers auto-detach
    info = parent.route.nodes()
    assert "child" not in info.get("routers", {})
    assert parent.child is None


def test_attach_instance_rejects_other_parent_when_already_bound():
    class Child(RoutingClass):
        pass

    class Parent(RoutingClass):
        def __init__(self, label: str):
            self.label = label
            self.child = Child()

    first = Parent("first")
    second = Parent("second")

    # Bind to first parent
    first.attach_instance(first.child, name="child")
    # Verify child is attached via node()
    assert first.route.node("child")

    # Attempt to bind same child to another parent should fail
    with pytest.raises(ValueError):
        second.attach_instance(first.child, name="child")


def test_routing_proxy_attach_instance():
    """Test routing.attach_instance delegates to the owner's attach_instance."""

    class Child(RoutingClass):
        @route()
        def hello(self):
            return "hello from child"

    class Parent(RoutingClass):
        def __init__(self):
            self.child = Child()

    parent = Parent()
    # Use routing.attach_instance proxy (delegates to owner)
    parent.routing.attach_instance(parent.child, name="child")

    # Verify child is accessible
    assert parent.route.node("child/hello")() == "hello from child"


def test_routing_proxy_instance():
    """Test routing.instance() returns child RoutingClass instance."""

    class UsersModule(RoutingClass):
        @route()
        def list(self):
            return "users:list"

    class OrdersModule(RoutingClass):
        @route()
        def list(self):
            return "orders:list"

    class App(RoutingClass):
        def __init__(self):
            self.attach_instance(UsersModule(), name="users")
            self.attach_instance(OrdersModule(), name="orders")

    app = App()

    # Retrieve child instances via routing.instance()
    users = app.routing.instance("users")
    orders = app.routing.instance("orders")

    assert isinstance(users, UsersModule)
    assert isinstance(orders, OrdersModule)

    # Routing still works
    assert app.route.node("users/list")() == "users:list"
    assert app.route.node("orders/list")() == "orders:list"


def test_routing_proxy_instance_not_found():
    """Test routing.instance() raises KeyError for non-existent child."""

    class App(RoutingClass):
        pass

    app = App()
    with pytest.raises(KeyError):
        app.routing.instance("nonexistent")


def test_endpoint_id_basic_lookup():
    """Test @endpoint_id resolution via node()."""

    class Service(RoutingClass):
        @route(endpoint_id="USR-001/1")
        def list_users(self):
            return "users"

        @route(endpoint_id="USR-002/1")
        def get_user(self, user_id):
            return f"user:{user_id}"

    svc = Service()

    # Resolve by endpoint_id
    node = svc.route.node("@USR-001/1")
    assert node() == "users"
    assert node.endpoint_id == "USR-001/1"

    # Resolve by path still works
    assert svc.route.node("list_users")() == "users"

    # endpoint_id with positional args via call
    node2 = svc.route.node("@USR-002/1")
    assert node2(42) == "user:42"


def test_endpoint_id_in_child_router():
    """Test @endpoint_id lookup across child routers."""

    class UsersModule(RoutingClass):
        @route(endpoint_id="USR-LIST")
        def list(self):
            return "users:list"

    class App(RoutingClass):
        def __init__(self):
            self.attach_instance(UsersModule(), name="users")

    app = App()

    # Endpoint_id found in child
    node = app.route.node("@USR-LIST")
    assert node() == "users:list"
    assert node.path == "users/list"
    assert node.endpoint_id == "USR-LIST"


def test_endpoint_id_not_found():
    """Test @endpoint_id returns not_found for unknown id."""

    class Service(RoutingClass):
        @route()
        def hello(self):
            return "hello"

    svc = Service()
    node = svc.route.node("@NONEXISTENT")
    assert node.error == "not_found"


def test_endpoint_id_accessible_from_path_node():
    """Test endpoint_id is accessible on nodes resolved by path."""

    class Service(RoutingClass):
        @route(endpoint_id="MY-EP")
        def handler(self):
            return "ok"

        @route()
        def no_id(self):
            return "no id"

    svc = Service()

    # Has endpoint_id
    assert svc.route.node("handler").endpoint_id == "MY-EP"

    # No endpoint_id
    assert svc.route.node("no_id").endpoint_id is None


def test_section_creates_hierarchy():
    """Grouping via composition (one RoutingClass per surface) builds hierarchies."""

    class Users(RoutingClass):
        @route()
        def list_users(self):
            return ["alice", "bob"]

    class Orders(RoutingClass):
        @route()
        def list_orders(self):
            return ["order1", "order2"]

    class Service(RoutingClass):
        def __init__(self):
            self.users = Users()
            self.orders = Orders()
            self.attach_instance(self.users, name="users")
            self.attach_instance(self.orders, name="orders")

    svc = Service()

    # Verify hierarchy structure via nodes()
    info = svc.route.nodes()
    assert "users" in info.get("routers", {})
    assert "orders" in info.get("routers", {})

    # Verify path resolution works
    assert svc.route.node("users/list_users")() == ["alice", "bob"]
    assert svc.route.node("orders/list_orders")() == ["order1", "order2"]


def test_include_router_on_nested_router():
    """Test include(Router) for direct router-to-router linking. Closes #28."""

    class SysApp(RoutingClass):
        @route()
        def status(self):
            return "ok"

    class Server(RoutingClass):
        def __init__(self):
            self._sys = Section()
            self.attach_instance(self._sys, name="_sys")
            self.swagger = SysApp()
            self._sys.route.include(self.swagger.route, name="swagger")

    server = Server()

    # Reachable through hierarchy
    assert server.route.node("_sys/swagger/status")() == "ok"

    # _routing_parent set on the owner (the Section owning the linking router)
    assert server.swagger._routing_parent is server._sys


def test_include_router_without_name_uses_router_name():
    """Test include(Router) without name uses the router's name ("route") as alias."""

    class Child(RoutingClass):
        @route()
        def invoice(self):
            return "inv"

    class Parent(RoutingClass):
        pass

    parent = Parent()
    child = Child()
    parent.route.include(child.route)
    assert parent.route.node("route/invoice")() == "inv"


def test_include_node_as_entry_alias():
    """Test include(RouterNode) creates an entry alias."""

    class Pagamenti(RoutingClass):
        @route()
        def collega_a_fattura(self, pag_id, fat_id):
            return f"linked:{pag_id}-{fat_id}"

    class Fatture(RoutingClass):
        @route()
        def lista(self):
            return "fatture"

    pag = Pagamenti()
    fat = Fatture()

    # Include the entry as alias
    fat.route.include(pag.route.node("collega_a_fattura"), name="collega_pagamento")

    # Original still works
    assert pag.route.node("collega_a_fattura")(1, 2) == "linked:1-2"

    # Alias works on fatture
    assert fat.route.node("collega_pagamento")(3, 4) == "linked:3-4"

    # Original entries still there
    assert fat.route.node("lista")() == "fatture"


def test_include_node_requires_name():
    """Test include(RouterNode) raises ValueError without name."""

    class Svc(RoutingClass):
        @route()
        def action(self):
            return "ok"

    svc = Svc()
    parent = Svc()
    with pytest.raises(ValueError, match="requires name"):
        parent.route.include(svc.route.node("action"))


def test_include_rejects_invalid_type():
    """Test include() raises TypeError for invalid source."""

    class Parent(RoutingClass):
        pass

    parent = Parent()
    with pytest.raises(TypeError, match="Router or RouterNode"):
        parent.route.include(object(), name="x")


def test_include_router_secondary_link_no_plugin_inheritance():
    """Secondary include() of a Router already attached elsewhere
    must NOT trigger plugin inheritance or change _routing_parent."""

    class Child(RoutingClass):
        @route()
        def action(self):
            return "child"

    class MainParent(RoutingClass):
        def __init__(self):
            self.route.plug("logging")

    class AltParent(RoutingClass):
        pass

    main = MainParent()
    alt = AltParent()
    child = Child()

    # Primary include — sets _routing_parent, inherits plugins
    main.route.include(child.route, name="primary")
    assert child._routing_parent is main
    original_plugins = list(child.route._plugins)

    # Secondary include — just a navigation link
    alt.route.include(child.route, name="secondary")

    # _routing_parent unchanged
    assert child._routing_parent is main

    # Both paths work
    assert main.route.node("primary/action")() == "child"
    assert alt.route.node("secondary/action")() == "child"

    # Plugins not duplicated on child
    assert len(child.route._plugins) == len(original_plugins)


def test_include_entry_alias_not_affected_by_dest_plugins():
    """An aliased entry must use the source router's plugins, not destination's."""

    class Svc(RoutingClass):
        def __init__(self, label):
            self.label = label
            self.route.plug("logging")

        @route()
        def action(self):
            return f"{self.label}:action"

    source = Svc("source")
    dest = Svc("dest")

    # Include source's entry as alias in dest
    dest.route.include(source.route.node("action"), name="alias_action")

    # Alias executes the source's handler (bound to source instance)
    assert dest.route.node("alias_action")() == "source:action"

    # Dest's own entry still works
    assert dest.route.node("action")() == "dest:action"


def test_include_entry_alias_survives_rebuild_handlers():
    """Alias entry's handler must not be overwritten by dest router's _rebuild_handlers."""

    class Source(RoutingClass):
        @route()
        def compute(self):
            return "computed"

    class Dest(RoutingClass):
        @route()
        def local(self):
            return "local"

    source = Source()
    dest = Dest()

    dest.route.include(source.route.node("compute"), name="remote_compute")

    # Force rebuild
    dest.route._rebuild_handlers()

    # Alias still works with source's handler
    assert dest.route.node("remote_compute")() == "computed"
    # Local still works
    assert dest.route.node("local")() == "local"


def test_include_entry_alias_with_plugins_on_dest():
    """Adding a plugin to dest after including an alias must not wrap the alias."""

    class Source(RoutingClass):
        @route()
        def handler(self):
            return "source"

    class Dest(RoutingClass):
        @route()
        def local(self):
            return "local"

    source = Source()
    dest = Dest()

    # Include alias first
    dest.route.include(source.route.node("handler"), name="remote")

    # Add plugin to dest after alias
    dest.route.plug("logging")

    # Alias entry should not have been decorated by dest's logging plugin
    alias_entry = dest.route._entries["remote"]
    assert alias_entry.router is source.route  # still owned by source

    # Both still work
    assert dest.route.node("remote")() == "source"
    assert dest.route.node("local")() == "local"


def test_include_router_collision():
    """include() of a Router with existing alias raises ValueError."""

    class Child1(RoutingClass):
        pass

    class Child2(RoutingClass):
        pass

    class Parent(RoutingClass):
        pass

    parent = Parent()
    parent.route.include(Child1().route, name="slot")
    with pytest.raises(ValueError, match="Child name collision"):
        parent.route.include(Child2().route, name="slot")


def test_include_entry_collision():
    """include() of a RouterNode with existing entry name raises ValueError."""

    class Svc(RoutingClass):
        @route()
        def action(self):
            return "svc"

    class Other(RoutingClass):
        @route()
        def action(self):
            return "other"

    svc = Svc()
    other = Other()
    with pytest.raises(ValueError, match="Entry name collision"):
        svc.route.include(other.route.node("action"), name="action")


def test_include_same_router_twice_is_idempotent():
    """Including the same Router with the same alias twice is a no-op."""

    class Child(RoutingClass):
        @route()
        def action(self):
            return "ok"

    class Parent(RoutingClass):
        pass

    parent = Parent()
    child = Child()
    parent.route.include(child.route, name="child")
    parent.route.include(child.route, name="child")  # no error
    assert parent.route.node("child/action")() == "ok"


def test_include_entry_from_deep_path():
    """include() with a node resolved from a deep hierarchy path."""

    class Deep(RoutingClass):
        @route()
        def deep_action(self):
            return "deep"

    class Mid(RoutingClass):
        def __init__(self):
            self.deep = Deep()
            self.attach_instance(self.deep, name="deep")

    class Root(RoutingClass):
        def __init__(self):
            self.mid = Mid()
            self.attach_instance(self.mid, name="mid")

    class Other(RoutingClass):
        @route()
        def local(self):
            return "local"

    root = Root()
    other = Other()

    # Include a deep entry as alias
    other.route.include(root.route.node("mid/deep/deep_action"), name="shortcut")

    assert other.route.node("shortcut")() == "deep"
    assert other.route.node("local")() == "local"


def test_include_node_with_error_raises():
    """include() with a RouterNode that has an error raises ValueError."""

    class Svc(RoutingClass):
        pass

    svc = Svc()
    node = svc.route.node("nonexistent")  # error node
    with pytest.raises(ValueError, match="no entry resolved"):
        svc.route.include(node, name="alias")


def test_get_url_with_endpoint_id():
    """Test get_url resolves @endpoint_id and appends positional params."""

    class Invoices(RoutingClass):
        @route(endpoint_id="invoice.list")
        def list(self):
            return "list"

        @route(endpoint_id="invoice.detail")
        def detail(self, invoice_id):
            return f"detail:{invoice_id}"

    class App(RoutingClass):
        def __init__(self):
            self.invoices = Invoices()
            self.attach_instance(self.invoices, name="invoices")

    app = App()

    # Without params
    assert app.route.get_url("@invoice.list") == "invoices/list"

    # With positional param
    assert app.route.get_url("@invoice.detail", invoice_id=123) == "invoices/detail/123"


def test_get_url_with_path():
    """Test get_url with a regular path (not endpoint_id)."""

    class Svc(RoutingClass):
        @route()
        def action(self, xx, yy):
            return f"{xx}:{yy}"

    class App(RoutingClass):
        def __init__(self):
            self.svc = Svc()
            self.attach_instance(self.svc, name="svc")

    app = App()
    assert app.route.get_url("svc/action", xx=23, yy="abc") == "svc/action/23/abc"


def test_get_url_preserves_param_order():
    """get_url appends params in signature order, regardless of kwarg order."""

    class Svc(RoutingClass):
        @route()
        def handler(self, first, second, third):
            pass

    svc = Svc()
    # Pass kwargs in reverse order
    url = svc.route.get_url("handler", third="c", first="a", second="b")
    assert url == "handler/a/b/c"


def test_get_url_partial_params():
    """get_url with only some params appends only those present."""

    class Svc(RoutingClass):
        @route()
        def handler(self, required, optional="default"):
            pass

    svc = Svc()
    assert svc.route.get_url("handler", required=42) == "handler/42"
    assert svc.route.get_url("handler", required=42, optional="x") == "handler/42/x"


def test_get_url_no_params():
    """get_url without params returns just the path."""

    class Svc(RoutingClass):
        @route()
        def simple(self):
            return "ok"

    svc = Svc()
    assert svc.route.get_url("simple") == "simple"


def test_get_url_invalid_path():
    """get_url raises ValueError for non-existent path."""

    class Svc(RoutingClass):
        pass

    svc = Svc()
    with pytest.raises(ValueError, match="does not resolve"):
        svc.route.get_url("nonexistent")


def test_get_url_deep_hierarchy():
    """get_url works through deep hierarchies."""

    class Deep(RoutingClass):
        @route(endpoint_id="deep.action")
        def action(self, x, y):
            return f"{x}:{y}"

    class Mid(RoutingClass):
        def __init__(self):
            self.deep = Deep()
            self.attach_instance(self.deep, name="deep")

    class Root(RoutingClass):
        def __init__(self):
            self.mid = Mid()
            self.attach_instance(self.mid, name="mid")

    root = Root()

    # Via path
    assert root.route.get_url("mid/deep/action", x=1, y=2) == "mid/deep/action/1/2"

    # Via endpoint_id
    assert root.route.get_url("@deep.action", x=1, y=2) == "mid/deep/action/1/2"


def test_get_url_ignores_keyword_only_params():
    """get_url does not append keyword-only params to the path."""

    class Svc(RoutingClass):
        @route()
        def handler(self, pos_param, *, kw_only="default"):
            pass

    svc = Svc()
    assert svc.route.get_url("handler", pos_param=10, kw_only="ignore") == "handler/10"


def _make_router_for_plugin_test():
    """Create a minimal router for testing plugin behavior."""

    class Owner(RoutingClass):
        pass

    return Owner().route


def test_base_plugin_default_hooks():
    router = _make_router_for_plugin_test()

    class TestPlugin(BasePlugin):
        plugin_code = "testplugin"
        plugin_description = "Test plugin"

        def configure(self, **config):
            pass  # Storage is handled by the wrapper

    Router.register_plugin(TestPlugin)
    router.plug("testplugin")
    plugin = router._plugins_by_name["testplugin"]
    entry = MethodEntry(name="foo", func=lambda: "ok", router=router, plugins=[])
    plugin.on_decore(router, entry.func, entry)
    assert plugin.wrap_handler(router, entry, lambda: "ok")() == "ok"


def test_logging_plugin_emit_without_handlers(capsys):
    router = _make_router_for_plugin_test()
    router.plug("logging")
    plugin = router._plugins_by_name["logging"]

    class DummyLogger:
        def has_handlers(self):
            return False

        # Compatibility alias
        hasHandlers = has_handlers  # noqa: N815

    plugin._logger = DummyLogger()  # type: ignore[attr-defined]
    plugin._emit("hello")
    captured = capsys.readouterr()
    assert captured.out == ""


def test_logging_plugin_emit_falls_back_to_print_when_log_enabled(capsys):
    router = _make_router_for_plugin_test()
    router.plug("logging")
    plugin = router._plugins_by_name["logging"]

    class DummyLogger:
        def has_handlers(self):
            return False

        # Compatibility alias
        hasHandlers = has_handlers  # noqa: N815

        def info(self, message):
            raise AssertionError("Should not be called")

    plugin._logger = DummyLogger()  # type: ignore[attr-defined]
    plugin._emit("hello", cfg={"log": True, "print": False})
    captured = capsys.readouterr()
    assert "hello" in captured.out


def test_pydantic_plugin_handles_hint_errors(monkeypatch):
    router = _make_router_for_plugin_test()
    router.plug("pydantic")
    plugin = router._plugins_by_name["pydantic"]
    entry = MethodEntry(name="foo", func=lambda **kw: "ok", router=router, plugins=[])

    def broken_get_type_hints(func):
        raise RuntimeError("boom")

    monkeypatch.setattr(pyd_mod, "get_type_hints", broken_get_type_hints)

    def handler():
        return "ok"

    plugin.on_decore(router, handler, entry)
    wrapper = plugin.wrap_handler(router, entry, lambda **kw: "ok")
    assert wrapper() == "ok"


def test_builtin_plugins_registered():
    available = Router.available_plugins()
    assert "logging" in available
    assert "pydantic" in available
    assert "auth" in available
    assert "env" in available
    assert "openapi" in available


def test_register_plugin_validates():
    with pytest.raises(TypeError):
        Router.register_plugin(object)  # type: ignore[arg-type]

    class CustomPlugin(BasePlugin):
        plugin_code = "custom_edge"
        plugin_description = "Custom test plugin"

    Router.register_plugin(CustomPlugin)

    class OtherPlugin(BasePlugin):
        plugin_code = "custom_edge"  # same code, different class
        plugin_description = "Other test plugin"

    with pytest.raises(ValueError):
        Router.register_plugin(OtherPlugin)


def test_router_get_config_paths():
    class CfgPlugin(BasePlugin):
        plugin_code = "cfgplug"
        plugin_description = "Config test plugin"

        def configure(self, **config):
            pass  # Storage is handled by the wrapper

    Router.register_plugin(CfgPlugin)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("cfgplug", mode="x")
            # Per-handler config via configure()
            self.route._plugins_by_name["cfgplug"].configure(_target="hello", trace=True)

        @route()
        def hello(self):
            return "ok"

    svc = Service()
    assert svc.route.get_config("cfgplug")["mode"] == "x"
    merged = svc.route.get_config("cfgplug", "hello")
    assert merged["mode"] == "x" and merged["trace"] is True
    with pytest.raises(AttributeError):
        svc.route.get_config("missing")


def test_routed_proxy_get_router_handles_dotted_path():
    class Leaf(RoutingClass):
        pass

    class Parent(RoutingClass):
        def __init__(self):
            self.child = Leaf()
            self.route._children["child"] = self.child.route  # direct attach for test

    svc = Parent()
    router = svc.routing.get_router("child")
    assert router is svc.child.route
    assert router.name == "route"


def test_routed_configure_updates_plugins_global_and_local():
    ensure_plugin(SimplePlugin)

    class ConfService(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

        @route()
        def foo(self):
            return "foo"

        @route()
        def bar(self):
            return "bar"

    svc = ConfService()
    svc.route.nodes()  # Trigger lazy binding before configure
    svc.routing.configure("simple/_all_", threshold=10)
    assert svc.route.simple.configuration()["threshold"] == 10

    svc.routing.configure("simple/foo", enabled=False)
    assert svc.route.simple.configuration("foo")["enabled"] is False

    svc.routing.configure("simple/b*", mode="strict")
    assert svc.route.simple.configuration("bar")["mode"] == "strict"

    payload = [
        {"target": "simple/_all_", "flags": "trace"},
        {"target": "simple/foo", "limit": 5},
    ]
    result = svc.routing.configure(payload)
    assert len(result) == 2
    assert svc.route.simple.configuration("foo")["limit"] == 5


def test_routed_configure_question_lists_tree():
    ensure_plugin(SimplePlugin)

    class Root(RoutingClass):
        def __init__(self):
            self.route.plug("simple")

        @route()
        def root_ping(self):
            return "root"

    svc = Root()
    info = svc.routing.configure("?")
    assert info["name"] == "route"
    assert info["plugins"]
    assert "root_ping" in info["entries"]
    assert info["routers"] == {}
