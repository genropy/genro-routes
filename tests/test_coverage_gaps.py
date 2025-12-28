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

"""Tests to cover remaining coverage gaps."""

import pytest

import genro_routes.plugins.logging  # noqa: F401
import genro_routes.plugins.pydantic  # noqa: F401
from genro_routes import RoutingClass, Router, route
from genro_routes.plugins._base_plugin import BasePlugin

# --- base_router.py:682 - _describe_entry_extra returns extra ---


def test_nodes_with_plugin_returns_extra_info():
    """Test that nodes() includes plugin info when plugins are attached."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def handler(self, text: str) -> str:
            return text

    svc = Svc()
    tree = svc.api.nodes()
    # Should have plugins info in entry
    entry_info = tree["entries"]["handler"]
    assert "plugins" in entry_info


# --- router.py:130 - _PluginSpec.clone ---


def test_plugin_spec_clone():
    """Test _PluginSpec.clone() method."""
    from genro_routes.core.router import _PluginSpec

    class DummyPlugin(BasePlugin):
        plugin_code = "dummy_clone"
        plugin_description = "Dummy for clone test"

    spec = _PluginSpec(DummyPlugin, {"option": "value"})
    cloned = spec.clone()
    assert cloned.factory is spec.factory
    assert cloned.kwargs == spec.kwargs
    assert cloned.kwargs is not spec.kwargs  # Should be a copy


# --- router.py:175 - empty plugin name error ---


def test_register_plugin_empty_name_raises():
    """Test that registering plugin with empty name raises ValueError."""

    class NoCodePlugin(BasePlugin):
        plugin_code = ""
        plugin_description = "No code"

    # Empty plugin_code is treated as missing plugin_code
    with pytest.raises(ValueError, match="missing plugin_code"):
        Router.register_plugin(NoCodePlugin)


# --- router.py:335-341, 353-355 - inherited plugin config lookup ---


def test_inherited_plugin_config_lookup():
    """Test that child router inherits parent plugin config."""

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = ChildSvc()  # Child must be an attribute of parent

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()

    # Set config on parent
    parent.api.logging.configure(before=False, after=True)

    # Attach child to parent
    parent.api.attach_instance(parent.child, name="child")

    # Child should inherit the plugin and config
    assert "logging" in parent.child.api._plugins_by_name

    # The config lookup should work (callable resolution)
    child_logging = parent.child.api._plugins_by_name["logging"]
    cfg = child_logging.configuration("child_handler")
    # Should have inherited config (before=False, after=True from parent)
    assert cfg.get("after") is True
    assert cfg.get("before") is False


# --- _base_plugin.py:119-122 - multi-target configure ---


def test_configure_multi_target():
    """Test configure() with comma-separated targets."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def handler_a(self):
            return "a"

        @route("api")
        def handler_b(self):
            return "b"

        @route("api")
        def handler_c(self):
            return "c"

    svc = Svc()
    # Configure multiple targets at once
    svc.api.logging.configure(_target="handler_a,handler_b", before=False)

    # Both should have before=False
    cfg_a = svc.api.logging.configuration("handler_a")
    cfg_b = svc.api.logging.configuration("handler_b")
    cfg_c = svc.api.logging.configuration("handler_c")

    assert cfg_a.get("before") is False
    assert cfg_b.get("before") is False
    # handler_c should not be affected (uses base)
    assert cfg_c.get("before") is not False or "before" not in cfg_c


# --- _base_plugin.py:240-241 - base configure with flags ---


def test_base_plugin_configure_with_flags():
    """Test BasePlugin.configure() with flags parameter."""

    class FlagsPlugin(BasePlugin):
        plugin_code = "flags_test"
        plugin_description = "Test flags in base configure"

        # No custom configure - uses base implementation

    Router.register_plugin(FlagsPlugin)

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("flags_test")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    # Call configure with flags - should use base implementation
    svc.api.flags_test.configure(flags="enabled,verbose:off")

    cfg = svc.api.flags_test.configuration("handler")
    assert cfg.get("enabled") is True
    assert cfg.get("verbose") is False


# --- pydantic.py:100 - no parameter hints ---


def test_pydantic_handler_without_param_hints():
    """Test pydantic plugin with handler that has no parameter hints."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def no_hints(self, x, y):  # No type hints on parameters
            return f"{x}:{y}"

    svc = Svc()
    # Should work without validation (passthrough)
    node = svc.api.node("no_hints")
    result = node("a", "b")
    assert result == "a:b"


def test_pydantic_handler_only_return_hint():
    """Test pydantic plugin with handler that has only return hint."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def only_return(self, x, y) -> str:  # Only return type hint
            return f"{x}:{y}"

    svc = Svc()
    # Should work without validation (no param hints after removing return)
    node = svc.api.node("only_return")
    result = node("a", "b")
    assert result == "a:b"


# --- pydantic.py:107 - param not in signature raises error ---


def test_pydantic_hint_not_in_signature_raises():
    """Test pydantic raises error when type hint doesn't match signature.

    When a handler has a type hint for a parameter that doesn't exist
    in the function signature, pydantic plugin should raise ValueError.
    """

    # Define function with annotation for non-existent param
    def handler(self, x: str) -> str:
        return x

    # Add annotation for parameter not in signature
    handler.__annotations__["phantom"] = int

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

    # Assign decorated handler - this triggers on_decore
    Svc.handler = route("api")(handler)

    # Error is raised at first use (lazy binding)
    svc = Svc()
    with pytest.raises(ValueError, match="type hint for 'phantom'.*not in the function signature"):
        svc.api.node("handler")


# --- pydantic.py:159-167 - get_model disabled/no model ---


def test_pydantic_get_model_disabled():
    """Test get_model returns None when disabled."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def handler(self, text: str) -> str:
            return text

    svc = Svc()
    svc.api.nodes()  # Trigger lazy binding
    entry = svc.api._entries["handler"]

    # Initially should return model
    result = svc.api.pydantic.get_model(entry)
    assert result is not None
    assert result[0] == "pydantic_model"

    # After disabling, should return None
    svc.api.pydantic.configure(disabled=True)
    result = svc.api.pydantic.get_model(entry)
    assert result is None


def test_pydantic_get_model_no_model():
    """Test get_model returns None when no model was created."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def no_hints(self, x, y):  # No type hints
            return f"{x}:{y}"

    svc = Svc()
    svc.api.nodes()  # Trigger lazy binding
    entry = svc.api._entries["no_hints"]

    # No model was created
    result = svc.api.pydantic.get_model(entry)
    assert result is None


# --- pydantic.py:164-173 - entry_metadata with signature info ---


def test_pydantic_entry_metadata_no_hints():
    """Test entry_metadata returns signature info even without type hints."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def no_hints(self, x, y):  # No type hints but signature is captured
            return f"{x}:{y}"

    svc = Svc()
    svc.api.nodes()  # Trigger lazy binding
    entry = svc.api._entries["no_hints"]

    result = svc.api.pydantic.entry_metadata(svc.api, entry)
    # Now always returns signature info (accepts_varargs, hints)
    assert result["accepts_varargs"] is False
    assert result["hints"] == {}
    assert result["model"] is None


def test_pydantic_entry_metadata_with_meta():
    """Test entry_metadata returns model info when pydantic metadata exists."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("pydantic")

        @route("api")
        def with_hints(self, text: str, num: int) -> str:
            return f"{text}:{num}"

    svc = Svc()
    svc.api.nodes()  # Trigger lazy binding
    entry = svc.api._entries["with_hints"]

    result = svc.api.pydantic.entry_metadata(svc.api, entry)
    assert "model" in result
    assert "hints" in result
    assert "accepts_varargs" in result
    assert result["hints"] == {"text": str, "num": int}
    assert result["accepts_varargs"] is False


# --- Plugin inheritance: clone + config copy ---


def test_inherited_plugin_is_separate_instance():
    """Test that inherited plugin is a new instance, not shared with parent."""

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.attach_instance(parent.child, name="child")

    # Plugin instances should be DIFFERENT objects
    parent_plugin = parent.api._plugins_by_name["logging"]
    child_plugin = parent.child.api._plugins_by_name["logging"]

    assert parent_plugin is not child_plugin
    assert parent_plugin._router is parent.api
    assert child_plugin._router is parent.child.api


def test_inherited_plugin_copies_parent_config():
    """Test that child inherits a copy of parent's config at attach time."""

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()

    # Configure parent BEFORE attach
    parent.api.logging.configure(before=False, after=True)

    # Attach child - should copy config
    parent.api.attach_instance(parent.child, name="child")

    # Child should have same config values
    child_cfg = parent.child.api.logging.configuration()
    assert child_cfg.get("before") is False
    assert child_cfg.get("after") is True


def test_child_config_independent_from_parent():
    """Test that after attach, child's config is independent from parent."""

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.logging.configure(before=True, after=False)
    parent.api.attach_instance(parent.child, name="child")

    # Child modifies its own config
    parent.child.api.logging.configure(before=False, after=True)

    # Configs should be different
    parent_cfg = parent.api.logging.configuration()
    child_cfg = parent.child.api.logging.configuration()

    assert parent_cfg.get("before") is True
    assert parent_cfg.get("after") is False
    assert child_cfg.get("before") is False
    assert child_cfg.get("after") is True


# --- on_parent_config_changed notification ---


def test_parent_config_change_notifies_children():
    """Test that changing parent config calls on_parent_config_changed on children."""
    notifications = []

    class TrackingPlugin(BasePlugin):
        plugin_code = "tracking"
        plugin_description = "Tracks parent config changes"

        def configure(self, value: int = 0):
            pass

        def on_parent_config_changed(self, old_config, new_config):
            notifications.append({"router": self._router.name, "config": new_config})

    Router.register_plugin(TrackingPlugin)

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="parent_api").plug("tracking")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.attach_instance(parent.child, name="child")

    # Clear any notifications from __init__
    notifications.clear()

    # Change parent config
    parent.api.tracking.configure(value=42)

    # Child should have been notified
    assert len(notifications) == 1
    assert notifications[0]["router"] == "child_api"
    assert notifications[0]["config"]["value"] == 42


def test_cascading_notifications():
    """Test that if child applies config, its children are also notified."""
    notifications = []

    class CascadePlugin(BasePlugin):
        plugin_code = "cascade"
        plugin_description = "Cascades config to children"

        def configure(self, level: int = 0, enabled: bool = True):
            pass

        def on_parent_config_changed(self, old_config, new_config):
            notifications.append({"router": self._router.name, "config": new_config})
            # Apply the config - this should cascade to our children
            self.configure(**new_config)

    Router.register_plugin(CascadePlugin)

    class GrandchildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="grandchild_api")

        @route("api")
        def grandchild_handler(self):
            return "grandchild"

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")
            self.grandchild = GrandchildSvc()

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="parent_api").plug("cascade")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.attach_instance(parent.child, name="child")
    parent.child.api.attach_instance(parent.child.grandchild, name="grandchild")

    # Clear notifications
    notifications.clear()

    # Change parent config
    parent.api.cascade.configure(level=99)

    # Both child and grandchild should have been notified
    assert len(notifications) == 2
    routers_notified = [n["router"] for n in notifications]
    assert "child_api" in routers_notified
    assert "grandchild_api" in routers_notified


def test_child_ignores_parent_config_no_cascade():
    """Test that if child ignores parent config, grandchildren are NOT notified."""
    notifications = []

    class IgnorePlugin(BasePlugin):
        plugin_code = "ignore"
        plugin_description = "Ignores parent config changes"

        def configure(self, value: int = 0):
            pass

        def on_parent_config_changed(self, old_config, new_config):
            notifications.append({"router": self._router.name, "config": new_config})
            # Do NOT call configure - stop the cascade

    Router.register_plugin(IgnorePlugin)

    class GrandchildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="grandchild_api")

        @route("api")
        def grandchild_handler(self):
            return "grandchild"

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")
            self.grandchild = GrandchildSvc()

        @route("api")
        def child_handler(self):
            return "child"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="parent_api").plug("ignore")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.attach_instance(parent.child, name="child")
    parent.child.api.attach_instance(parent.child.grandchild, name="grandchild")

    # Clear notifications
    notifications.clear()

    # Change parent config
    parent.api.ignore.configure(value=77)

    # Only child should be notified (grandchild NOT because child ignores)
    assert len(notifications) == 1
    assert notifications[0]["router"] == "child_api"


# --- exceptions.py: test selector format ---


def test_not_found_selector():
    """Test NotFound exception with selector."""
    from genro_routes.exceptions import NotFound

    exc = NotFound("my_router:my_path")
    assert exc.selector == "my_router:my_path"
    assert "my_router:my_path" in str(exc)


def test_not_authorized_selector():
    """Test NotAuthorized exception with selector."""
    from genro_routes.exceptions import NotAuthorized

    exc = NotAuthorized("my_router:my_path")
    assert exc.selector == "my_router:my_path"
    assert "my_router:my_path" in str(exc)


def test_not_authenticated_selector():
    """Test NotAuthenticated exception with selector."""
    from genro_routes.exceptions import NotAuthenticated

    exc = NotAuthenticated("my_router:my_path")
    assert exc.selector == "my_router:my_path"
    assert "my_router:my_path" in str(exc)


def test_not_available_selector():
    """Test NotAvailable exception with selector."""
    from genro_routes.exceptions import NotAvailable

    exc = NotAvailable("my_router:my_path")
    assert exc.selector == "my_router:my_path"
    assert "my_router:my_path" in str(exc)


# --- auth.py: deny_reason with RouterInterface ---


def test_auth_deny_reason_with_router_interface():
    """Test auth plugin deny_reason when passed a RouterInterface (child router)."""

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")

        @route("api", auth_rule="admin")
        def admin_only(self):
            return "admin"

        @route("api")
        def public(self):
            return "public"

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="parent_api").plug("auth")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.attach_instance(parent.child, name="child")

    # Get child router via parent
    child_router = parent.api._children["child"]

    # Test deny_reason with RouterInterface
    auth_plugin = parent.api._plugins_by_name["auth"]

    # Without tags - should return "" because public handler exists
    result = auth_plugin.deny_reason(child_router)
    assert result == ""  # At least one entry is allowed (public)

    # With admin tags - should return ""
    result = auth_plugin.deny_reason(child_router, tags="admin")
    assert result == ""


def test_auth_deny_reason_router_empty():
    """Test auth deny_reason with empty router returns empty string."""

    class ChildSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")
            # No routes defined

    class ParentSvc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="parent_api").plug("auth")
            self.child = ChildSvc()

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = ParentSvc()
    parent.api.attach_instance(parent.child, name="child")

    child_router = parent.api._children["child"]
    auth_plugin = parent.api._plugins_by_name["auth"]

    # Empty router returns "" (no entries to check)
    result = auth_plugin.deny_reason(child_router)
    assert result == ""


# --- openapi.py: edge cases ---


def test_openapi_translator_schema_to_parameters_empty():
    """Test schema_to_parameters with empty schema."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    result = OpenAPITranslator.schema_to_parameters({})
    assert result == []

    result = OpenAPITranslator.schema_to_parameters({"properties": {}})
    assert result == []


def test_openapi_translator_entry_without_callable():
    """Test entry_info_to_openapi when callable is None."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    entry_info = {
        "callable": None,
        "doc": "Some documentation",
    }
    result = OpenAPITranslator.entry_info_to_openapi("test_entry", entry_info)

    # Should default to POST when no callable
    assert "post" in result
    assert result["post"]["operationId"] == "test_entry"


def test_openapi_translator_create_model_no_fields():
    """Test create_pydantic_model_for_func returns None when no fields."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    def no_params() -> str:
        return "ok"

    # No params except return → no model
    result = OpenAPITranslator.create_pydantic_model_for_func(no_params)
    assert result is None


def test_openapi_h_openapi_child_included():
    """Test h_openapi includes child routers with metadata."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    nodes_data = {
        "entries": {},
        "routers": {
            "child": {
                "entries": {},
                "routers": {},
                "description": "A child router",
            }
        },
    }
    result = OpenAPITranslator.translate_h_openapi(nodes_data, lazy=False)

    # Child is included (has description metadata)
    assert "routers" in result
    assert "child" in result["routers"]
    assert result["routers"]["child"]["description"] == "A child router"


# --- base_router.py: additional coverage ---


def test_get_default_handler_constructor_param():
    """Test get_default_handler constructor parameter (line 154)."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api", get_default_handler="index")

        @route("api")
        def index(self):
            return "index"

        @route("api")
        def other(self):
            return "other"

    svc = Svc()
    # Default handler should be index
    assert svc.api.default_entry == "index"


def test_add_entry_with_meta_kwargs():
    """Test add_entry with meta_* kwargs (lines 261-263, 376-378)."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api", meta_author="John", meta_version="1.0")
        def handler(self):
            return "ok"

    svc = Svc()
    node = svc.api.node("handler")
    # meta_ kwargs should be grouped under "meta" key
    assert node.metadata.get("author") == "John"
    assert node.metadata.get("version") == "1.0"


def test_nodes_with_pattern_filter():
    """Test nodes() with pattern filter (line 721)."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_users(self):
            return []

        @route("api")
        def get_orders(self):
            return []

        @route("api")
        def create_user(self):
            return {}

    svc = Svc()
    # Filter by pattern
    nodes = svc.api.nodes(pattern="^get_")
    entries = nodes.get("entries", {})
    assert "get_users" in entries
    assert "get_orders" in entries
    assert "create_user" not in entries


def test_entry_invalid_reason_with_none():
    """Test _entry_invalid_reason with None entry (lines 903-905)."""
    from genro_routes.core.base_router import BaseRouter

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    # Access internal method - entry is None should return "not_found"
    result = svc.api._entry_invalid_reason(None)
    assert result == "not_found"
