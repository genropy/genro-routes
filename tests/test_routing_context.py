# Copyright 2025-2026 Softwell S.r.l.
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

"""Tests for RoutingContext and slot-based ctx property on RoutingClass."""

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


class TestCtxSlot:
    """Test slot-based ctx property on RoutingClass."""

    def test_default_none(self):
        """ctx returns None when not set."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        assert svc.ctx is None

    def test_set_and_get(self):
        """Set and get ctx via property."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        ctx = RoutingContext()
        ctx.db = "test_db"
        svc.ctx = ctx
        assert svc.ctx is ctx
        assert svc.ctx.db == "test_db"

    def test_clear_ctx(self):
        """Setting ctx to None clears the local slot."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Svc()
        ctx = RoutingContext()
        svc.ctx = ctx
        assert svc.ctx is ctx
        svc.ctx = None
        assert svc.ctx is None

    def test_parent_chain_lookup(self):
        """ctx walks up _routing_parent chain."""
        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        parent = Parent()
        child = Child()
        parent.attach_instance(child, name="child")

        ctx = RoutingContext()
        ctx.db = "shared_db"
        parent.ctx = ctx

        # Child walks up to parent's ctx
        assert child.ctx is ctx
        assert child.ctx.db == "shared_db"

    def test_child_override(self):
        """Child can set its own ctx, overriding parent's."""
        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        parent = Parent()
        child = Child()
        parent.attach_instance(child, name="child")

        parent_ctx = RoutingContext()
        parent_ctx.label = "parent"
        parent.ctx = parent_ctx

        child_ctx = RoutingContext()
        child_ctx.label = "child"
        child.ctx = child_ctx

        assert parent.ctx.label == "parent"
        assert child.ctx.label == "child"

    def test_clear_child_falls_through_to_parent(self):
        """Clearing child's ctx makes it fall through to parent."""
        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        parent = Parent()
        child = Child()
        parent.attach_instance(child, name="child")

        parent_ctx = RoutingContext()
        parent_ctx.label = "parent"
        parent.ctx = parent_ctx

        child_ctx = RoutingContext()
        child_ctx.label = "child"
        child.ctx = child_ctx
        assert child.ctx.label == "child"

        # Clear child's local ctx
        child.ctx = None
        # Falls through to parent
        assert child.ctx is parent_ctx
        assert child.ctx.label == "parent"

    def test_instances_are_independent(self):
        """Two unrelated instances have independent ctx slots."""
        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        a = Svc()
        b = Svc()

        ctx_a = RoutingContext()
        ctx_a.label = "a"
        a.ctx = ctx_a

        # b does not see a's ctx (no parent chain between them)
        assert b.ctx is None
        assert a.ctx.label == "a"

    def test_no_contextvar_import(self):
        """Verify ContextVar is not imported in routing.py."""
        import genro_routes.core.routing as mod
        source = open(mod.__file__).read()
        assert "from contextvars" not in source
        assert "ContextVar" not in source
