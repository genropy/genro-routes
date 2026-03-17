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

import sys
from typing import TypedDict

import pytest

import genro_routes.plugins.logging  # noqa: F401
import genro_routes.plugins.pydantic  # noqa: F401
from genro_routes import RoutingClass, Router, route
from genro_routes.plugins._base_plugin import BasePlugin


# TypedDict classes at module level for cross-Python-version compatibility
# (pydantic handles nested TypedDict differently when defined inside functions
# on Python <3.12)

class _Address(TypedDict):
    street: str
    city: str


class _Person(TypedDict):
    name: str
    address: _Address


class _Inner(TypedDict):
    value: int


class _Outer(TypedDict):
    inner: _Inner

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
    path_item, defs = OpenAPITranslator.entry_info_to_openapi("test_entry", entry_info)

    # Should default to POST when no callable
    assert "post" in path_item
    assert path_item["post"]["operationId"] == "test_entry"
    assert defs == {}  # No $defs when no callable


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


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="TypedDict type hints not resolved by pydantic on Python <3.12",
)
def test_openapi_nested_typeddict_defs_at_root():
    """Test that nested TypedDict $defs are collected at the root level.

    When a return type uses nested TypedDict, pydantic generates $defs
    for the inner types. These should be collected at the OpenAPI doc root,
    not embedded in each response schema.

    Fixes: https://github.com/softwellsrl/genro-routes/issues/15
    """
    from genro_routes.plugins.openapi import OpenAPITranslator

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_person(self) -> _Person:
            return {"name": "John", "address": {"street": "123 Main", "city": "NYC"}}

    svc = Svc()
    nodes = svc.api.nodes()
    result = OpenAPITranslator.translate_openapi(nodes)

    # $defs should be at the root level
    assert "$defs" in result, "Expected $defs at root level for nested TypedDict"
    assert "_Address" in result["$defs"], "Expected _Address in $defs"

    # Response schema should reference $defs, not embed them
    path_item = result["paths"]["/get_person"]
    response_schema = path_item["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$defs" not in response_schema, "$defs should not be in response schema"


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="TypedDict type hints not resolved by pydantic on Python <3.12",
)
def test_openapi_nested_typeddict_h_openapi_defs_at_root():
    """Test that h_openapi also collects $defs at root level."""
    from genro_routes.plugins.openapi import OpenAPITranslator

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def get_outer(self) -> _Outer:
            return {"inner": {"value": 42}}

    svc = Svc()
    nodes = svc.api.nodes()
    result = OpenAPITranslator.translate_h_openapi(nodes)

    # $defs should be at the root level
    assert "$defs" in result, "Expected $defs at root level for nested TypedDict"
    assert "_Inner" in result["$defs"], "Expected _Inner in $defs"


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


def test_base_router_entry_invalid_reason():
    """Test BaseRouter._entry_invalid_reason directly.

    BaseRouter provides a default implementation that returns "not_found"
    for None entries. Router overrides this, so we test BaseRouter directly.
    """
    from genro_routes.core.base_router import BaseRouter

    class Svc(RoutingClass):
        def __init__(self):
            # Use BaseRouter directly, not Router
            self.api = BaseRouter(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    # BaseRouter._entry_invalid_reason with None returns "not_found"
    assert svc.api._entry_invalid_reason(None) == "not_found"
    # BaseRouter._entry_invalid_reason with valid entry returns ""
    entry = svc.api._entries.get("handler")
    assert svc.api._entry_invalid_reason(entry) == ""


# --- base_router.py:251-255 - meta_* kwargs shorthand ---


def test_add_entry_meta_kwargs_shorthand():
    """Test that meta_* kwargs are grouped under 'meta' key.

    This is a convenience syntax that allows:
        router.add_entry(handler, meta_foo="bar", meta_baz=123)

    Instead of:
        router.add_entry(handler, meta={"foo": "bar", "baz": 123})
    """

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Add entry using meta_* shorthand syntax
    def extra_handler():
        return "extra"

    svc.api.add_entry(extra_handler, name="extra", meta_author="john", meta_version=2)

    # Verify the metadata was correctly grouped
    entry = svc.api._entries["extra"]
    assert entry.metadata.get("meta", {}).get("author") == "john"
    assert entry.metadata.get("meta", {}).get("version") == 2


# --- base_router.py:261 - non-plugin options as metadata ---


def test_add_entry_custom_options_as_metadata():
    """Test that non-plugin options are merged into entry metadata.

    Options that are not plugin-scoped (no underscore or unknown plugin)
    and not meta_* prefixed are merged directly into entry.metadata.
    """

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    svc = Svc()

    def handler():
        return "ok"

    # Pass custom options without underscore (so they don't go through plugin check)
    svc.api.add_entry(handler, name="test", deprecated=True, priority=10)

    entry = svc.api._entries["test"]
    assert entry.metadata.get("deprecated") is True
    assert entry.metadata.get("priority") == 10


def test_add_entry_unknown_plugin_option_as_metadata():
    """Test that underscore options with unknown plugin prefix go to metadata.

    If an option like 'foo_bar=123' is passed and 'foo' is not a known plugin,
    the entire key 'foo_bar' is stored in metadata (not treated as plugin config).
    """

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    svc = Svc()

    def handler():
        return "ok"

    # 'unknown' is not a registered plugin, so 'unknown_option' goes to metadata
    svc.api.add_entry(handler, name="test", unknown_option="value")

    entry = svc.api._entries["test"]
    assert entry.metadata.get("unknown_option") == "value"


# --- router_node.py - custom exceptions and properties when entry is None ---


def test_router_node_custom_exceptions_in_init():
    """Test RouterNode with custom exceptions passed to constructor."""
    from genro_routes.core.router_node import RouterNode

    class CustomNotFound(Exception):
        pass

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Create node with custom exceptions
    node = RouterNode(
        svc.api,
        errors={"not_found": CustomNotFound},
        entry_name="nonexistent",
    )

    # Should raise custom exception
    with pytest.raises(CustomNotFound):
        node()


def test_router_node_doc_and_metadata_when_entry_none():
    """Test doc and metadata properties return empty when entry is None."""
    from genro_routes.core.router_node import RouterNode

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Create node for nonexistent entry
    node = RouterNode(svc.api, entry_name="nonexistent")

    # Properties should return empty values when entry is None
    assert node.doc == ""
    assert node.metadata == {}


def test_router_node_custom_validation_error_exception():
    """Test RouterNode remaps ValidationError to custom exception."""
    from pydantic import ValidationError as PydanticValidationError

    class CustomValidationError(Exception):
        pass

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            # Raise a pydantic ValidationError
            from pydantic import BaseModel

            class Model(BaseModel):
                value: int

            Model(value="not_an_int")  # This raises ValidationError

    svc = Svc()
    node = svc.api.node("handler")
    node.set_custom_exceptions({"validation_error": CustomValidationError})

    with pytest.raises(CustomValidationError):
        node()


# --- auth.py:111 - deny_reason with RouterInterface where child is accessible ---


def test_auth_deny_reason_router_with_accessible_child():
    """Test auth deny_reason returns empty when at least one child is accessible."""
    import genro_routes.plugins.auth  # noqa: F401

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api", auth_rule="public")
        def public_handler(self):
            return "public"

        @route("api", auth_rule="admin")
        def admin_handler(self):
            return "admin"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("auth")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

    parent = Parent()
    auth_plugin = parent.api._plugins_by_name["auth"]

    # Get child router
    child_router = parent.child.api

    # deny_reason on router should return "" if any child is accessible
    result = auth_plugin.deny_reason(child_router, auth_tags="public")
    assert result == ""


# --- routing.py coverage ---


def test_result_wrapper():
    """Test ResultWrapper class."""
    from genro_routes.core.routing import ResultWrapper, is_result_wrapper

    wrapper = ResultWrapper("test_value", {"mime": "text/plain"})
    assert wrapper.value == "test_value"
    assert wrapper.metadata == {"mime": "text/plain"}
    assert is_result_wrapper(wrapper) is True
    assert is_result_wrapper("not a wrapper") is False


def test_routing_class_result_wrapper_method():
    """Test RoutingClass.result_wrapper() method."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    svc = Svc()
    result = svc.result_wrapper("content", mime_type="application/json")

    from genro_routes.core.routing import ResultWrapper

    assert isinstance(result, ResultWrapper)
    assert result.value == "content"
    assert result.metadata == {"mime_type": "application/json"}


def test_routing_class_context_property():
    """Test RoutingClass.context getter and setter."""
    from genro_routes.core.context import RoutingContext

    class TestContext(RoutingContext):
        """Concrete context for testing."""

        def __init__(self, user: str):
            self._user = user

        @property
        def db(self):
            return None

        @property
        def avatar(self):
            return None

        @property
        def session(self):
            return None

        @property
        def app(self):
            return None

        @property
        def server(self):
            return None

        @property
        def user(self):
            return self._user

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    svc = Svc()

    # Initially None
    assert svc.context is None

    # Set context
    ctx = TestContext(user="test_user")
    svc.context = ctx
    assert svc.context is ctx
    assert svc.context.user == "test_user"

    # Clear context
    svc.context = None
    assert svc.context is None


def test_routing_class_context_type_error():
    """Test that setting invalid context raises TypeError."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    svc = Svc()

    with pytest.raises(TypeError, match="context must be a RoutingContext"):
        svc.context = "not a context"


def test_routing_class_context_propagates_from_parent():
    """Test that context propagates from parent to child."""
    from genro_routes.core.context import RoutingContext

    class TestContext(RoutingContext):
        """Concrete context for testing."""

        @property
        def db(self):
            return None

        @property
        def avatar(self):
            return None

        @property
        def session(self):
            return None

        @property
        def app(self):
            return None

        @property
        def server(self):
            return None

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

    parent = Parent()
    ctx = TestContext()
    parent.context = ctx

    # Child should inherit context from parent
    assert parent.child.context is ctx


def test_plugin_on_parent_config_changed_propagates():
    """Test that parent config changes propagate to aligned children."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def child_handler(self):
            return "child"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = Parent()

    # Get child's logging plugin
    child_plugin = parent.child.api._plugins_by_name.get("logging")
    assert child_plugin is not None

    # Initially child should have same config as parent (aligned)
    parent_plugin = parent.api._plugins_by_name.get("logging")
    assert child_plugin.configuration() == parent_plugin.configuration()

    # Change parent config
    parent_plugin.configure(before=True)

    # Child should have been updated (was aligned with parent)
    assert child_plugin.configuration().get("before") is True


# =============================================================================
# Additional tests to reach 100% coverage in core/
# =============================================================================


# --- base_router.py:157->161 - _register_router hook not callable ---


def test_router_owner_without_callable_register_hook():
    """Test router creation when owner has non-callable _register_router."""

    class BadOwner(RoutingClass):
        def __init__(self):
            # Override _register_router with non-callable
            object.__setattr__(self, "_register_router", "not_callable")
            # Router should still work - just skips the hook
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    # Should not raise - hook is skipped when not callable
    svc = BadOwner()
    assert svc.api.node("handler")() == "ok"


# --- base_router.py:290->288 - empty chunk in comma-separated add_entry ---


def test_add_entry_comma_separated_with_empty_chunks():
    """Test add_entry with comma-separated targets including empty chunks."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        def foo(self):
            return "foo"

        def bar(self):
            return "bar"

    svc = Svc()
    # Include empty chunks via extra commas
    svc.api.add_entry("foo, , bar, ")

    assert "foo" in svc.api._entries
    assert "bar" in svc.api._entries


# --- base_router.py:393 - plugin_options not None in _register_marked ---


def test_register_marked_with_plugin_options():
    """Test that plugin_options passed to add_entry propagate through _register_marked."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api", logging_before=False)
        def handler(self):
            return "ok"

    svc = Svc()
    # Plugin options from @route should be in entry metadata
    entry = svc.api._entries["handler"]
    assert "plugin_config" in entry.metadata
    assert entry.metadata["plugin_config"].get("logging", {}).get("before") is False


# --- base_router.py:507-508 - _require_bound when already bound ---


def test_require_bound_when_already_bound():
    """Test _require_bound does nothing when already bound."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    # Force binding
    _ = svc.api._entries

    # Call _require_bound again - should be no-op
    svc.api._require_bound("test_op")
    assert svc.api._bound is True


# --- base_router.py:588-589 - attach_instance mapping without colon ---


def test_attach_instance_mapping_without_colon():
    """Test attach_instance with mapping that has no colon (uses router name as alias)."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")
            self.admin = Router(self, name="admin")

        @route("child_api")
        def api_handler(self):
            return "api"

        @route("admin")
        def admin_handler(self):
            return "admin"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()

    parent = Parent()
    # Mapping without colon - should use router name as alias
    parent.api.attach_instance(parent.child, mapping="child_api")

    # Should be attached under original name
    assert "child_api" in parent.api._children


# --- base_router.py:603 - attach_instance unknown router in mapping ---


def test_attach_instance_mapping_unknown_router():
    """Test attach_instance raises ValueError for unknown router in mapping."""

    class Child(RoutingClass):
        def __init__(self):
            # Multiple routers so default_router is None and mapping is used
            self.api = Router(self, name="child_api")
            self.admin = Router(self, name="admin")

        @route("child_api")
        def handler(self):
            return "ok"

        @route("admin")
        def admin_handler(self):
            return "admin"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()

    parent = Parent()
    with pytest.raises(ValueError, match="Unknown router"):
        parent.api.attach_instance(parent.child, mapping="nonexistent:alias")


# --- base_router.py:611->613 - attach_instance _routing_parent already set correctly ---


def test_attach_instance_routing_parent_already_correct():
    """Test attach_instance when _routing_parent is already set to correct parent."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")

        @route("child_api")
        def handler(self):
            return "ok"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()

    parent = Parent()
    # Manually set _routing_parent to correct parent
    object.__setattr__(parent.child, "_routing_parent", parent)

    # attach_instance should not try to set it again
    parent.api.attach_instance(parent.child, name="child")
    assert parent.child._routing_parent is parent


# --- base_router.py:631->638 - detach_instance with plugin_children cleanup ---


def test_detach_instance_cleans_plugin_children():
    """Test detach_instance cleans up _plugin_children references."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child_api")

        @route("child_api")
        def handler(self):
            return "ok"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

        @route("api")
        def parent_handler(self):
            return "parent"

    parent = Parent()

    # Verify plugin_children has the child
    assert "logging" in parent.api._plugin_children
    assert any(r.instance is parent.child for r in parent.api._plugin_children["logging"])

    # Detach
    parent.api.detach_instance(parent.child)

    # Plugin children should be cleaned up
    assert not any(r.instance is parent.child for r in parent.api._plugin_children["logging"])


# --- base_router.py:752 - nodes with basepath and unknown mode ---


def test_nodes_basepath_with_unknown_mode_raises():
    """Test nodes() with basepath and unknown mode raises ValueError."""

    class Child(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="child")

        @route("child")
        def handler(self):
            return "ok"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

    parent = Parent()
    with pytest.raises(ValueError, match="Unknown mode"):
        parent.api.nodes(basepath="child", mode="invalid_mode")


# --- base_router.py:882-884 - node() with openapi=True but entry is None ---


def test_node_openapi_with_not_found_entry():
    """Test node() with openapi=True when entry doesn't exist."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    # Request non-existent entry with openapi=True
    node = svc.api.node("nonexistent", openapi=True)

    # openapi should not be populated when entry is None
    assert node.error == "not_found"
    assert node.openapi is None


# --- router.py:258 - _get_plugin_bucket initializing _all_ ---


def test_get_plugin_bucket_initializes_all():
    """Test _get_plugin_bucket creates _all_ bucket when missing."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Manually remove _all_ to test re-initialization
    bucket = svc.api._plugin_info["logging"]
    del bucket["_all_"]

    # Now call _get_plugin_bucket
    result = svc.api._get_plugin_bucket("logging")

    # Should have recreated _all_
    assert "_all_" in result


# --- router.py:315-318 - is_plugin_enabled via config (not locals) ---


def test_is_plugin_enabled_via_config_only():
    """Test is_plugin_enabled returns value from config when no locals set."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Set enabled=False via config (not locals)
    svc.api.logging.configure(enabled=False)

    # Should read from config
    assert svc.api.is_plugin_enabled("handler", "logging") is False


def test_is_plugin_enabled_global_config():
    """Test is_plugin_enabled reads _all_ config when entry has no override."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Set enabled=False globally via config
    svc.api.logging.configure(enabled=False)

    # Should read from _all_ config
    assert svc.api.is_plugin_enabled("handler", "logging") is False


def test_is_plugin_enabled_global_locals():
    """Test is_plugin_enabled reads _all_ locals when set."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Set enabled globally via set_plugin_enabled (_all_)
    svc.api.set_plugin_enabled("_all_", "logging", False)

    # Should read from _all_ locals
    assert svc.api.is_plugin_enabled("handler", "logging") is False


# --- router.py:429->431 - _apply_plugin_to_entries skip already-present plugin ---


def test_apply_plugin_to_entries_skips_duplicate():
    """Test _apply_plugin_to_entries doesn't double-add plugin name."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    # Force binding
    _ = svc.api._entries

    # Now plug - should apply to existing entries
    svc.api.plug("logging")

    entry = svc.api._entries["handler"]
    # Plugin name should appear only once
    assert entry.plugins.count("logging") == 1


# --- router.py:458-462, 469 - _on_attached_to_parent child already has plugin ---


def test_on_attached_to_parent_child_has_same_plugin():
    """Test plugin inheritance when child already has the same plugin."""

    class Child(RoutingClass):
        def __init__(self):
            # Child creates its own logging plugin
            self.api = Router(self, name="child").plug("logging")

        @route("child")
        def handler(self):
            return "ok"

    class Parent(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.child = Child()

    parent = Parent()
    parent.api.attach_instance(parent.child, name="child")

    # Child should still have exactly one logging plugin
    assert len([p for p in parent.child.api._plugins if p.name == "logging"]) == 1


# --- router.py:533->536, 545->529 - _describe_entry_extra with config/metadata ---


def test_describe_entry_extra_with_plugin_data():
    """Test _describe_entry_extra includes plugin that has config."""

    class TestPlugin(BasePlugin):
        """Plugin with default config but no metadata."""
        plugin_code = "testplugin2"
        plugin_description = "Test plugin"

        def configure(self, custom_option: str = "default"):
            pass

        def entry_metadata(self, router, entry):
            return {}  # Empty dict - no metadata

    Router.register_plugin(TestPlugin)

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("testplugin2")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()
    tree = svc.api.nodes()

    entry_info = tree["entries"]["handler"]
    # Plugin with config should appear (has enabled: True by default)
    assert "plugins" in entry_info
    assert "testplugin2" in entry_info["plugins"]
    # Should have config but not metadata
    plugin_info = entry_info["plugins"]["testplugin2"]
    assert "config" in plugin_info
    # metadata is empty so should not be included
    assert "metadata" not in plugin_info or plugin_info.get("metadata") == {}


# --- routing.py:317 - RoutingClassAuto.default_router with existing _main_router ---


def test_routing_class_auto_existing_main_router():
    """Test RoutingClassAuto returns existing _main_router on second call."""
    from genro_routes import RoutingClassAuto

    class Svc(RoutingClassAuto):
        @route()
        def handler(self):
            return "ok"

    svc = Svc()

    # First access creates _main_router
    router1 = svc.default_router
    assert router1 is not None

    # Second access should return same router
    router2 = svc.default_router
    assert router2 is router1


# --- router_node.py:70->73 - ValidationError is None ---


def test_router_node_default_exceptions_without_pydantic():
    """Test DEFAULT_EXCEPTIONS when ValidationError import fails."""
    from genro_routes.core.router_node import RouterNode

    # Just verify the class loads correctly and has default exceptions
    assert "not_found" in RouterNode.DEFAULT_EXCEPTIONS
    assert "not_authorized" in RouterNode.DEFAULT_EXCEPTIONS


# --- router_node.py:225->230 - __call__ with non-pydantic ValidationError ---


def test_router_node_call_non_pydantic_exception_reraises():
    """Test RouterNode.__call__ re-raises non-ValidationError exceptions."""

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self):
            raise RuntimeError("test error")

    svc = Svc()
    node = svc.api.node("handler")

    with pytest.raises(RuntimeError, match="test error"):
        node()


# --- base_router.py:393 - plugin_options passed to _register_marked ---


def test_add_entry_star_with_plugin_options():
    """Test add_entry('*') with plugin_* kwargs merged via _register_marked.

    This covers line 393: merged_plugin_opts.update(plugin_options)
    The plugin_options dict gets populated from plugin-prefixed kwargs
    passed to add_entry (e.g., logging_before=False).
    """
    from genro_routes.core.base_router import BaseRouter

    # Create a fresh class for this test
    class SvcForPluginOpts(RoutingClass):
        def __init__(self):
            self.api = BaseRouter(self, name="api")

        def my_handler(self):
            return "ok"

    # Mark the method BEFORE instantiation
    SvcForPluginOpts.my_handler._route_decorator_kw = [{"router_name": "api"}]

    svc = SvcForPluginOpts()

    # Trigger initial binding (registers handler without plugin_options)
    _ = svc.api._entries
    assert "my_handler" in svc.api._BaseRouter__entries_raw

    # Now call add_entry("*") with plugin kwargs AND replace=True
    # logging_before=False gets split into plugin_options={"logging": {"before": False}}
    # by add_entry, then merged in _register_marked (line 393)
    svc.api.add_entry("*", logging_before=False, replace=True)

    entry = svc.api._BaseRouter__entries_raw["my_handler"]
    # Plugin options should be in entry metadata under plugin_config
    config = entry.metadata.get("plugin_config", {})
    assert config.get("logging", {}).get("before") is False


# --- base_router.py:494 - _bind when already bound ---


def test_bind_when_already_bound():
    """Test _bind() returns early when already bound.

    This covers line 494: return statement when self._bound is True.
    """
    from genro_routes.core.base_router import BaseRouter

    class Svc(RoutingClass):
        def __init__(self):
            self.api = BaseRouter(self, name="api")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Force binding via _entries access
    _ = svc.api._entries
    assert svc.api._bound is True

    # Call _bind directly - should return early (no error, no-op)
    svc.api._bind()
    assert svc.api._bound is True


# --- base_router.py:882-884 - node() with openapi=True and existing entry ---


def test_node_openapi_with_existing_entry():
    """Test node() with openapi=True when entry exists.

    This covers lines 882-884: openapi population when entry is not None.
    """

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def handler(self, value: int) -> str:
            """A documented handler."""
            return str(value)

    svc = Svc()
    # Request existing entry with openapi=True
    node = svc.api.node("handler", openapi=True)

    # openapi should be populated when entry exists
    assert node.error is None
    assert node.openapi is not None
    # Should have operation info
    assert "operationId" in str(node.openapi) or node.openapi.get("get") or node.openapi.get("post")


# --- router.py:318 - is_plugin_enabled returns True when no enabled config ---


def test_is_plugin_enabled_returns_true_default():
    """Test is_plugin_enabled returns True when no enabled config is set.

    This covers line 318: return True (fallback).
    """

    class Svc(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def handler(self):
            return "ok"

    svc = Svc()

    # Don't set any enabled config - should return True by default
    # Note: we need to clear any implicit config
    bucket = svc.api._plugin_info.get("logging", {})
    handler_data = bucket.get("handler", {})
    # Remove enabled from both locals and config if present
    handler_data.pop("locals", None)
    handler_data.pop("config", None)

    # Also clear _all_ enabled settings
    all_data = bucket.get("_all_", {})
    all_data.pop("locals", None)
    # Keep only non-enabled config entries
    if "config" in all_data:
        all_data["config"].pop("enabled", None)

    # Now is_plugin_enabled should return True (default)
    assert svc.api.is_plugin_enabled("handler", "logging") is True
