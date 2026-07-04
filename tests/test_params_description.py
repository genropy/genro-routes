# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for the dialect-neutral params block in nodes() and on RouterNode.

The params block is the input-side twin of the result block. Per entry it
exposes the aggregate input JSON Schema plus a per-parameter list (name,
schema, required, default, kind) and an accepts_varargs flag. It is produced
once by the pydantic plugin at decoration time and only read at runtime, so
nodes()/node().params never re-serialize a schema. It is present only when the
pydantic plugin captured params for the entry.
"""

from __future__ import annotations

from pydantic import BaseModel

from genro_routes import RoutingClass, route


class _Item(BaseModel):
    id: int
    tag: str


class ParamsService(RoutingClass):
    def __init__(self):
        self.route.plug("pydantic")

    @route()
    def search(self, user_id: int, limit: int = 20):
        return None

    @route()
    def mixed(self, user_id: int, note, *tags, flag: bool = False, **opts):
        return None

    @route()
    def create(self, item: _Item):
        return None

    @route()
    def noargs(self):
        return None


def _entries():
    return ParamsService().route.nodes()["entries"]


def _field(params, name):
    return next(f for f in params["fields"] if f["name"] == name)


def test_aggregate_schema_required_and_type():
    params = _entries()["search"]["params"]
    schema = params["schema"]
    assert schema["properties"]["user_id"]["type"] == "integer"
    assert schema["required"] == ["user_id"]


def test_fields_required_vs_default():
    params = _entries()["search"]["params"]
    user_id = _field(params, "user_id")
    limit = _field(params, "limit")
    assert user_id["required"] is True
    assert user_id["default"] is None
    assert limit["required"] is False
    assert limit["default"] == 20
    assert user_id["kind"] == "positional_or_keyword"
    assert limit["kind"] == "positional_or_keyword"


def test_unannotated_param_has_no_schema():
    params = _entries()["mixed"]["params"]
    note = _field(params, "note")
    assert note["schema"] is None
    assert note["required"] is True
    # unannotated param is absent from the aggregate model schema
    assert "note" not in params["schema"]["properties"]


def test_varargs_excluded_and_flagged():
    params = _entries()["mixed"]["params"]
    names = {f["name"] for f in params["fields"]}
    assert names == {"user_id", "note", "flag"}  # *tags / **opts excluded
    assert params["accepts_varargs"] is True


def test_keyword_only_kind():
    params = _entries()["mixed"]["params"]
    assert _field(params, "flag")["kind"] == "keyword_only"


def test_nested_model_param_has_defs():
    params = _entries()["create"]["params"]
    schema = params["schema"]
    # pydantic emits $defs for the nested model, referenced from the property
    assert "$defs" in schema
    assert "_Item" in schema["$defs"]
    assert "$ref" in schema["properties"]["item"]


def test_self_not_in_params():
    params = _entries()["search"]["params"]
    assert "self" not in params["schema"]["properties"]
    assert not any(f["name"] == "self" for f in params["fields"])


def test_noargs_block_present_but_empty():
    params = _entries()["noargs"]["params"]
    assert params["fields"] == []
    assert params["schema"] is None
    assert params["accepts_varargs"] is False


def test_no_params_block_without_pydantic_plugin():
    class NoPlugin(RoutingClass):
        @route()
        def handler(self, x: int):
            return None

    entries = NoPlugin().route.nodes()["entries"]
    assert "params" not in entries["handler"]


def test_params_at_runtime_via_node():
    svc = ParamsService()
    node = svc.route.node("search")
    assert {f["name"] for f in node.params["fields"]} == {"user_id", "limit"}


def test_node_params_empty_without_plugin():
    class NoPlugin(RoutingClass):
        @route()
        def handler(self, x: int):
            return None

    assert NoPlugin().route.node("handler").params == {}


def test_node_accepts():
    node = ParamsService().route.node("search")
    assert node.accepts("user_id") is True
    assert node.accepts("limit") is True
    assert node.accepts("nope") is False
    assert node.accepts("self") is False


def test_node_accepts_without_plugin_falls_back():
    class NoPlugin(RoutingClass):
        @route()
        def handler(self, item_id):
            return None

    node = NoPlugin().route.node("handler")
    assert node.accepts("item_id") is True
    assert node.accepts("nope") is False
