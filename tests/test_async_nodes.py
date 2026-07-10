# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for async-aware RouterNode classification (issue #42).

A node resolved from an ``async def`` handler must classify as a coroutine
function, so a classification-based dispatcher awaits it on the event loop
instead of running it in a thread. Sync handlers and not-found nodes must stay
non-coroutine. Execution itself already works: this only concerns
classification.

Assertions use ``asyncio.iscoroutinefunction`` — the signal issue #42 targets
and that downstream dispatchers use. On Python 3.11 the node is marked via the
asyncio sentinel (inspect.markcoroutinefunction is 3.12+), and only
``asyncio.iscoroutinefunction`` reports True there; on 3.12+ both do.
"""

from __future__ import annotations

import asyncio

from genro_routes import RoutingClass, route


class Api(RoutingClass):
    @route()
    def alfa(self) -> str:
        return "sync"

    @route()
    async def beta(self) -> str:
        return "async"


def test_sync_node_is_not_coroutine():
    node = Api().route.node("alfa")
    assert asyncio.iscoroutinefunction(node) is False
    assert node() == "sync"


def test_async_node_is_coroutine():
    node = Api().route.node("beta")
    assert asyncio.iscoroutinefunction(node) is True
    assert asyncio.run(node()) == "async"


def test_async_classification_survives_pydantic_plugin():
    # entry.handler is wrapped by the (sync) pydantic wrapper; the mark is on
    # entry.func, so the node stays classified as a coroutine function.
    class PApi(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        async def gamma(self, x: int) -> dict:
            return {"x": x}

    node = PApi().route.node("gamma")
    assert asyncio.iscoroutinefunction(node) is True
    assert asyncio.run(node(3)) == {"x": 3}


def test_async_node_with_path_segment():
    class SegApi(RoutingClass):
        @route()
        async def item(self, item_id) -> str:
            return f"item={item_id}"

    node = SegApi().route.node("item/42")
    assert asyncio.iscoroutinefunction(node) is True
    assert asyncio.run(node()) == "item=42"


def test_not_found_node_is_not_coroutine():
    node = Api().route.node("nope")
    assert node._entry is None
    assert asyncio.iscoroutinefunction(node) is False


def test_async_child_node_classified_through_hierarchy():
    class Child(RoutingClass):
        @route()
        async def ping(self) -> str:
            return "pong"

    class Parent(RoutingClass):
        def __init__(self):
            self.attach_instance(Child(), name="c")

    node = Parent().route.node("c/ping")
    assert asyncio.iscoroutinefunction(node) is True
    assert asyncio.run(node()) == "pong"
