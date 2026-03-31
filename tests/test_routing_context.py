"""Tests for RoutingContext and ContextVar-based context in RoutingClass."""

import contextvars

import pytest

from genro_routes import Router, RoutingClass, RoutingContext


class TestRoutingContextAttributes:
    """Test RoutingContext attribute storage and parent chain."""

    def test_set_and_get_attribute(self):
        """Direct attribute assignment and read."""
        ctx = RoutingContext()
        ctx.db = "my_db"
        assert ctx.db == "my_db"

    def test_parent_chain_delegation(self):
        """Missing attribute walks up to parent."""
        parent = RoutingContext()
        parent.db = "parent_db"
        child = RoutingContext(parent=parent)
        assert child.db == "parent_db"

    def test_local_override(self):
        """Local attribute shadows parent."""
        parent = RoutingContext()
        parent.db = "parent_db"
        child = RoutingContext(parent=parent)
        child.db = "child_db"
        assert child.db == "child_db"
        assert parent.db == "parent_db"

    def test_attribute_error_no_parent(self):
        """AttributeError raised when attribute missing and no parent."""
        ctx = RoutingContext()
        with pytest.raises(AttributeError, match="nonexistent"):
            _ = ctx.nonexistent

    def test_attribute_error_with_parent_chain(self):
        """AttributeError raised when attribute missing in entire chain."""
        root = RoutingContext()
        child = RoutingContext(parent=root)
        with pytest.raises(AttributeError):
            _ = child.nonexistent

    def test_deep_chain(self):
        """Attribute resolves through a 3-level chain."""
        root = RoutingContext()
        root.server = "the_server"
        mid = RoutingContext(parent=root)
        mid.app = "the_app"
        leaf = RoutingContext(parent=mid)
        leaf.request = "the_request"

        assert leaf.request == "the_request"
        assert leaf.app == "the_app"
        assert leaf.server == "the_server"

    def test_parent_accessible(self):
        """_parent is a normal attribute, not delegated."""
        parent = RoutingContext()
        child = RoutingContext(parent=parent)
        assert child._parent is parent

    def test_no_init_safe(self):
        """__getattr__ does not recurse if __init__ was never called."""
        ctx = object.__new__(RoutingContext)
        with pytest.raises(AttributeError):
            _ = ctx.anything


class TestContextVar:
    """Test ContextVar-based context on RoutingClass."""

    def test_default_none(self):
        """Context is None when not set."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        assert svc.context is None

    def test_set_and_get(self):
        """Set and get context via property."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        ctx = RoutingContext()
        ctx.db = "test_db"
        svc.context = ctx
        assert svc.context is ctx
        assert svc.context.db == "test_db"
        svc.context = None

    def test_shared_across_instances(self):
        """Two RoutingClass instances in same task share the ContextVar."""
        class SvcA(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        class SvcB(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        a = SvcA()
        b = SvcB()
        ctx = RoutingContext()
        a.context = ctx
        assert b.context is ctx
        a.context = None

    def test_isolation_via_copy_context(self):
        """ContextVar isolates across contextvars.copy_context() runs."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        outer_ctx = RoutingContext()
        outer_ctx.label = "outer"
        svc.context = outer_ctx

        inner_seen = []

        def run_in_copy():
            inner_ctx = RoutingContext()
            inner_ctx.label = "inner"
            svc.context = inner_ctx
            inner_seen.append(svc.context.label)

        ctx_copy = contextvars.copy_context()
        ctx_copy.run(run_in_copy)

        # Inner saw its own context
        assert inner_seen == ["inner"]
        # Outer context unchanged
        assert svc.context is outer_ctx
        assert svc.context.label == "outer"
        svc.context = None

    def test_accepts_any_value(self):
        """Setter accepts any value, no type check."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        svc.context = "not a RoutingContext"
        assert svc.context == "not a RoutingContext"
        svc.context = None
