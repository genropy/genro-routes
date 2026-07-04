# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for the dialect-neutral result block in nodes() and @route(media_type=...).

The result block exposes, per entry, the JSON Schema of the return type and the
declared media type, independent of any dialect (OpenAPI/MCP). It is present
only when a return schema and/or a media type exist.
"""

from __future__ import annotations

from pydantic import BaseModel

from genro_routes import RoutingClass, route


class _Row(BaseModel):
    id: int
    name: str


class ResultService(RoutingClass):
    def __init__(self):
        self.route.plug("pydantic")

    @route()
    def scalar(self) -> str:
        return "x"

    @route()
    def rows(self, limit: int | None = None) -> list[dict]:
        return [{}]

    @route()
    def typed_rows(self) -> list[_Row]:
        return []

    @route()
    def union(self) -> dict | list:
        return {}

    @route(media_type="text/html")
    def page(self) -> str:
        return "<h1>hi</h1>"

    @route(media_type="image/png")
    def binary(self):
        return b""

    @route()
    def untyped(self):
        return 1


def _entries():
    return ResultService().route.nodes()["entries"]


def test_scalar_return_schema():
    result = _entries()["scalar"]["result"]
    assert result["schema"] == {"type": "string"}
    assert result["media_type"] is None


def test_list_return_schema():
    schema = _entries()["rows"]["result"]["schema"]
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "object"


def test_typed_list_return_schema_has_defs():
    schema = _entries()["typed_rows"]["result"]["schema"]
    assert schema["type"] == "array"
    # pydantic emits $defs inline for the model item, referenced from items
    assert "$defs" in schema
    assert "_Row" in schema["$defs"]
    assert "$ref" in schema["items"]


def test_union_return_schema_is_anyof():
    schema = _entries()["union"]["result"]["schema"]
    assert "anyOf" in schema
    types = {arm.get("type") for arm in schema["anyOf"]}
    assert types == {"object", "array"}


def test_media_type_exposed_in_result_block():
    result = _entries()["page"]["result"]
    assert result["media_type"] == "text/html"
    assert result["schema"] == {"type": "string"}


def test_media_type_without_return_hint():
    # binary has media_type but no return annotation → schema None, media_type set
    result = _entries()["binary"]["result"]
    assert result["schema"] is None
    assert result["media_type"] == "image/png"


def test_no_result_block_without_schema_or_media_type():
    assert "result" not in _entries()["untyped"]


def test_media_type_at_runtime_via_node_metadata():
    svc = ResultService()
    assert svc.route.node("page").metadata == {"media_type": "text/html"}
    # no media_type declared → empty runtime metadata
    assert svc.route.node("rows").metadata == {}


def test_result_block_absent_without_pydantic_plugin():
    class NoPlugin(RoutingClass):
        @route()
        def handler(self) -> str:
            return "x"

    # No pydantic plugin → no response_schema producer; but media_type still surfaces
    entries = NoPlugin().route.nodes()["entries"]
    assert "result" not in entries["handler"]


def test_media_type_surfaces_without_pydantic_plugin():
    class NoPlugin(RoutingClass):
        @route(media_type="text/plain")
        def handler(self):
            return "x"

    entries = NoPlugin().route.nodes()["entries"]
    result = entries["handler"]["result"]
    assert result["media_type"] == "text/plain"
    assert result["schema"] is None
