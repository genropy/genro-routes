"""Tests for node() path resolution with nested routers."""

import pytest
from genro_routes import Router, RoutingClass, route


class DeepService(RoutingClass):
    """Third level: has *args default entry."""

    def __init__(self):
        self.api = Router(self, name="api", default_entry="index")

    @route("api")
    def index(self, *args):
        return f"deep.index: {args}"


class AdminService(RoutingClass):
    """Second level: has default entry with optional param."""

    def __init__(self):
        self.api = Router(self, name="api", default_entry="index")
        self.deep = DeepService()
        self.api.attach_instance(self.deep, name="deep")

    @route("api")
    def index(self, item_id=None):
        return f"admin.index: {item_id}"

    @route("api")
    def users(self):
        return "admin.users"


class RootService(RoutingClass):
    """Root level: has entries with various signatures."""

    def __init__(self):
        self.api = Router(self, name="api", default_entry="index")
        self.admin = AdminService()
        self.api.attach_instance(self.admin, name="admin")

    @route("api")
    def index(self):
        return "root.index"

    @route("api")
    def action(self, x, y):
        return f"root.action: {x}, {y}"


@pytest.fixture
def root():
    return RootService()


class TestDirectEntry:
    """Test resolving entries directly on the root router."""

    def test_action_no_partial(self, root):
        """node('action') resolves to root.action entry."""
        node = root.api.node("action")
        assert node.type == "entry"
        assert node.name == "action"
        assert node.partial == []
        assert node.partial_kwargs == {}

    def test_action_with_partial(self, root):
        """node('action/1/2') resolves to root.action with partial args."""
        node = root.api.node("action/1/2")
        assert node.type == "entry"
        assert node.name == "action"
        assert node.partial_kwargs == {"x": "1", "y": "2"}

    def test_index_direct(self, root):
        """node('index') resolves to root.index entry."""
        node = root.api.node("index")
        assert node.type == "entry"
        assert node.name == "index"


class TestDefaultEntry:
    """Test resolving via default_entry when path doesn't match entry."""

    def test_unknown_path_uses_default_entry(self, root):
        """node('zuz') should try default_entry 'index' with partial ['zuz']."""
        node = root.api.node("zuz")
        # root.index() has no params, so partial ['zuz'] won't fit
        # Node exists but calling it raises NotFound
        assert not node.is_callable

    def test_default_entry_with_matching_partial(self, root):
        """Admin's default_entry accepts optional param."""
        node = root.api.node("admin/zuz")
        assert node.type == "entry"
        assert node.name == "index"
        assert node.partial_kwargs == {"item_id": "zuz"}


class TestChildRouterNavigation:
    """Test navigating to child routers."""

    def test_child_router_direct(self, root):
        """node('admin') resolves to child router."""
        node = root.api.node("admin")
        assert node.type == "router"
        assert node.name == "api"  # AdminService's router name

    def test_child_entry(self, root):
        """node('admin/users') resolves to admin.users entry."""
        node = root.api.node("admin/users")
        assert node.type == "entry"
        assert node.name == "users"

    def test_deep_child_router(self, root):
        """node('admin/deep') resolves to deep child router."""
        node = root.api.node("admin/deep")
        assert node.type == "router"


class TestDeepPartialResolution:
    """Test partial resolution on deeply nested routers."""

    def test_deep_with_varargs(self, root):
        """node('admin/deep/foo/bar') resolves with *args partial."""
        node = root.api.node("admin/deep/foo/bar")
        assert node.type == "entry"
        assert node.name == "index"
        # 'foo' and 'bar' should be in extra_args since index uses *args
        assert node.extra_args == ["foo", "bar"]

    def test_deep_single_arg(self, root):
        """node('admin/deep/single') resolves with one arg."""
        node = root.api.node("admin/deep/single")
        assert node.type == "entry"
        assert node.name == "index"
        assert node.extra_args == ["single"]


class TestNotFound:
    """Test cases where node should not be found."""

    def test_too_many_args_for_signature(self, root):
        """node('action/1/2/3') - action takes 2 params, not 3."""
        node = root.api.node("action/1/2/3")
        # action takes 2 params, not 3 - calling raises NotFound
        assert not node.is_callable

    def test_nonexistent_child_no_default(self):
        """Router without default_entry returns not found for unknown path."""

        class NoDefaultService(RoutingClass):
            def __init__(self):
                # No default_entry set (will be "index" by default but no index method)
                self.api = Router(self, name="api")

            @route("api")
            def only_action(self):
                return "only"

        svc = NoDefaultService()
        node = svc.api.node("nonexistent")
        # No 'nonexistent' entry and no working default - calling raises NotFound
        assert not node.is_callable


class TestNodeInvocation:
    """Test that resolved nodes can be invoked correctly."""

    def test_invoke_simple_entry(self, root):
        """Invoking node('index') calls root.index()."""
        node = root.api.node("index")
        result = node()
        assert result == "root.index"

    def test_invoke_with_partial_kwargs(self, root):
        """Invoking node('action/a/b') passes partial as kwargs."""
        node = root.api.node("action/a/b")
        result = node()
        assert result == "root.action: a, b"

    def test_invoke_deep_with_extra_args(self, root):
        """Invoking deep entry passes extra_args."""
        node = root.api.node("admin/deep/x/y/z")
        result = node()
        assert result == "deep.index: ('x', 'y', 'z')"

    def test_invoke_child_entry(self, root):
        """Invoking admin/users works."""
        node = root.api.node("admin/users")
        result = node()
        assert result == "admin.users"
