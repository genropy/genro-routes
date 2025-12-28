"""Tests for node() path resolution with nested routers."""

import pytest
from genro_routes import Router, RoutingClass, route
from genro_routes.exceptions import NotFound


class AdminService(RoutingClass):
    """Child router with default entry accepting optional param."""

    def __init__(self):
        self.api = Router(self, name="api", default_entry="index")

    @route("api")
    def index(self, item_id=None):
        return f"admin.index: {item_id}"

    @route("api")
    def users(self):
        return "admin.users"


class RootService(RoutingClass):
    """Root router with entries and child router."""

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


class TestFindCandidateNode:
    """Test _find_candidate_node exit cases."""

    def test_empty_path_uses_default_entry(self, root):
        """Case 1: path.strip('/') is empty -> RouterNode(self)."""
        node = root.api.node("")
        assert node() == "root.index"

    def test_empty_path_with_slash(self, root):
        """Case 1 variant: '/' also resolves to default_entry."""
        node = root.api.node("/")
        assert node() == "root.index"

    def test_entry_found_with_partial(self, root):
        """Case 2: head in router._entries -> entry with partial args."""
        node = root.api.node("action/1/2")
        assert node() == "root.action: 1, 2"

    def test_child_router_uses_its_default_entry(self, root):
        """Case 3: consumed all path navigating children -> RouterNode(router)."""
        node = root.api.node("admin")
        assert node() == "admin.index: None"

    def test_head_not_entry_not_child_uses_default(self, root):
        """Case 4: head not entry nor child -> fallback to default_entry."""
        node = root.api.node("admin/zuz")
        assert node() == "admin.index: zuz"


class TestRouterNodeInit:
    """Test RouterNode.__init__ entry resolution."""

    def test_entry_found_and_partial_valid(self, root):
        """Entry found and _assign_partial returns True -> _entry populated."""
        node = root.api.node("action/a/b")
        assert node.error is None
        assert node() == "root.action: a, b"

    def test_entry_not_found(self, root):
        """default_entry doesn't accept partial -> _entry is None."""
        node = root.api.node("zuz")
        # root.index() has no params, so partial ['zuz'] won't fit
        with pytest.raises(NotFound):
            node()

    def test_too_many_args_for_signature(self, root):
        """Entry found but partial exceeds signature -> _entry is None."""
        node = root.api.node("action/1/2/3")
        with pytest.raises(NotFound):
            node()

    def test_no_default_entry_defined(self):
        """Router has no matching default_entry -> NotFound on call."""

        class NoDefaultService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def only_action(self):
                return "only"

        svc = NoDefaultService()
        node = svc.api.node("nonexistent")
        with pytest.raises(NotFound):
            node()
