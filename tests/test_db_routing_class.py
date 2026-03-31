"""Tests for DbRoutingClass."""

import pytest

from genro_routes import DbRoutingClass, Router, route


class FakeDb:
    """Minimal fake database for testing."""

    def __init__(self, name="default"):
        self.name = name

    def query(self, sql):
        return f"{self.name}:{sql}"


def test_db_direct_set_and_get():
    """Setting db on an instance makes it available via property."""

    class Svc(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db

    db = FakeDb()
    svc = Svc(db)
    assert svc.db is db


def test_db_raises_when_not_set():
    """AttributeError raised when no db in the chain."""

    class Svc(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    svc = Svc()
    with pytest.raises(AttributeError, match="No db available"):
        svc.db


def test_db_propagates_from_parent_to_child():
    """Child inherits db from parent via _routing_parent chain."""

    class Child(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    class Parent(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

    db = FakeDb()
    parent = Parent(db)
    assert parent.child.db is db


def test_db_child_override():
    """Child with its own db does not see parent's db."""

    class Child(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db

    class Parent(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db
            self.child = Child(FakeDb("child"))
            self.api.attach_instance(self.child, name="child")

    parent_db = FakeDb("parent")
    parent = Parent(parent_db)
    assert parent.db is parent_db
    assert parent.child.db.name == "child"


def test_db_deep_chain():
    """Db propagates through a 3-level chain."""

    class Leaf(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    class Middle(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")
            self.leaf = Leaf()
            self.api.attach_instance(self.leaf, name="leaf")

    class Root(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db
            self.middle = Middle()
            self.api.attach_instance(self.middle, name="middle")

    db = FakeDb("root")
    root = Root(db)
    assert root.middle.leaf.db is db


def test_db_set_none_falls_through():
    """Setting db to None makes the property fall through to parent."""

    class Child(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    class Parent(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db
            self.child = Child()
            self.api.attach_instance(self.child, name="child")

    db = FakeDb()
    parent = Parent(db)

    # Explicitly set child db then clear it
    parent.child.db = FakeDb("temp")
    assert parent.child.db.name == "temp"
    parent.child.db = None
    assert parent.child.db is db


def test_db_chain_breaks_at_plain_routing_class():
    """If a node in the chain is plain RoutingClass, chain breaks."""
    from genro_routes import RoutingClass

    class PlainMiddle(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    class DbChild(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

    class DbRoot(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db
            self.middle = PlainMiddle()
            self.api.attach_instance(self.middle, name="middle")
            self.middle.api.attach_instance(DbChild(), name="leaf")

    root = DbRoot(FakeDb())
    leaf = root.middle.api._children["leaf"].instance
    with pytest.raises(AttributeError):
        leaf.db


def test_db_in_handler():
    """Handler can use self.db inside a route."""

    class Svc(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db

        @route("api")
        def get_data(self):
            return self.db.query("SELECT 42")

    db = FakeDb("main")
    svc = Svc(db)
    result = svc.api.node("get_data")()
    assert result == "main:SELECT 42"
