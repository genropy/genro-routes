"""DbRoutingClass — RoutingClass with automatic db property propagation.

Provides ``DbRoutingClass``, a subclass of ``RoutingClass`` that adds a
``db`` property walking up the ``_routing_parent`` chain.

Example::

    from genro_routes import DbRoutingClass, Router, route

    class MyServer(DbRoutingClass):
        def __init__(self, db):
            self.api = Router(self, name="api")
            self.db = db

    class MyModule(DbRoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def query(self):
            return self.db.execute("SELECT 1")
"""

from __future__ import annotations

from .routing import RoutingClass

__all__ = ["DbRoutingClass"]


class DbRoutingClass(RoutingClass):
    """RoutingClass with automatic db property propagation.

    The ``db`` property walks up the ``_routing_parent`` chain. Any level
    can set ``self.db = my_db`` to override for itself and its children.
    If no db is found in the entire chain, ``AttributeError`` is raised.
    """

    __slots__ = ("_db",)

    @property
    def db(self):
        """Return the database connection, searching up the parent chain."""
        db = getattr(self, "_db", None)
        if db is not None:
            return db
        parent = getattr(self, "_routing_parent", None)
        if parent is not None:
            return parent.db
        raise AttributeError("No db available")

    @db.setter
    def db(self, value):
        """Set the database connection for this instance."""
        object.__setattr__(self, "_db", value)
