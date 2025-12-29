"""OpenAPI plugin for Genro Routes.

Provides explicit control over OpenAPI schema generation for handlers.
Use this plugin to override automatically guessed HTTP methods or add
OpenAPI-specific metadata like tags, summary, and description.

Configuration
-------------
Accepted keys (router-level or per-handler):
    - ``enabled``: Gate the plugin entirely (default True)
    - ``method``: HTTP method override (e.g., "get", "post", "delete")
    - ``tags``: OpenAPI tags (string or list of strings)
    - ``summary``: Summary override for the operation
    - ``deprecated``: Mark the operation as deprecated (default False)

Example::

    from genro_routes import Router, RoutingClass, route

    class MyService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("openapi")

        # Method will be guessed as POST (has parameters)
        @route("api")
        def get_item(self, item_id: int) -> dict:
            return {"id": item_id}

        # Explicit override to DELETE
        @route("api", openapi_method="delete")
        def delete_item(self, item_id: int) -> dict:
            return {"deleted": item_id}

        # Add tags
        @route("api", openapi_tags=["users", "admin"])
        def list_users(self) -> list:
            return []
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from genro_routes.core.router import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class OpenAPIPlugin(BasePlugin):
    """OpenAPI plugin for explicit schema control."""

    plugin_code = "openapi"
    plugin_description = "Provides explicit control over OpenAPI schema generation"

    def configure(  # type: ignore[override]
        self,
        enabled: bool = True,
        method: str | None = None,
        tags: str | list[str] | None = None,
        summary: str | None = None,
        deprecated: bool = False,
    ):
        """Configure OpenAPI plugin options.

        Args:
            enabled: Enable/disable the plugin entirely.
            method: HTTP method override (get, post, put, delete, patch).
            tags: OpenAPI tags for grouping operations.
            summary: Summary text override for the operation.
            deprecated: Mark the operation as deprecated.
        """
        pass  # Storage is handled by the wrapper

    def entry_metadata(self, router: Any, entry: MethodEntry) -> dict[str, Any]:
        """Provide OpenAPI-specific metadata for a handler.

        Returns:
            Dict containing openapi configuration for this handler.
        """
        cfg = self.configuration(entry.name)
        metadata: dict[str, Any] = {}

        if cfg.get("method"):
            metadata["method"] = cfg["method"]
        if cfg.get("tags"):
            metadata["tags"] = cfg["tags"]
        if cfg.get("summary"):
            metadata["summary"] = cfg["summary"]
        if cfg.get("deprecated"):
            metadata["deprecated"] = cfg["deprecated"]

        return {"openapi": metadata} if metadata else {}


Router.register_plugin(OpenAPIPlugin)


class OpenAPITranslator:
    """Translator for converting router nodes to OpenAPI format.

    This class provides static methods to translate the output of
    ``router.nodes()`` to OpenAPI-compatible formats.

    Two modes are supported:
    - ``openapi``: Flat format with all paths merged into a single paths dict.
    - ``h_openapi``: Hierarchical format preserving the router tree structure.
    """

    @staticmethod
    def translate_openapi(
        nodes_data: dict[str, Any],
        lazy: bool = False,
        path_prefix: str = "",
    ) -> dict[str, Any]:
        """Translate nodes() output to flat OpenAPI format.

        Args:
            nodes_data: Output from nodes() in standard format.
            lazy: If True, child routers are returned as router references.
            path_prefix: Prefix for generated paths (used internally for recursion).

        Returns:
            Dict with "paths" containing OpenAPI path items (flat structure),
            "$defs" containing all type definitions (if any nested types),
            and "routers" for children in lazy mode.
        """
        paths: dict[str, Any] = {}
        all_defs: dict[str, Any] = {}

        entries = nodes_data.get("entries", {})
        for entry_name, entry_info in entries.items():
            path = f"{path_prefix}/{entry_name}" if path_prefix else f"/{entry_name}"
            path_item, defs = OpenAPITranslator.entry_info_to_openapi(entry_name, entry_info)
            paths[path] = path_item
            all_defs.update(defs)

        routers_data = nodes_data.get("routers", {})
        routers: dict[str, Any]
        if lazy:
            routers = dict(routers_data)
        else:
            for child_name, child_data in routers_data.items():
                child_prefix = f"{path_prefix}/{child_name}" if path_prefix else f"/{child_name}"
                child_openapi = OpenAPITranslator.translate_openapi(
                    child_data, lazy=False, path_prefix=child_prefix
                )
                paths.update(child_openapi.get("paths", {}))
                # Collect $defs from children
                if "$defs" in child_openapi:
                    all_defs.update(child_openapi["$defs"])
            routers = {}

        result: dict[str, Any] = {"paths": paths}
        if all_defs:
            result["$defs"] = all_defs
        if routers:
            result["routers"] = routers
        return result

    @staticmethod
    def translate_h_openapi(
        nodes_data: dict[str, Any],
        lazy: bool = False,
    ) -> dict[str, Any]:
        """Translate nodes() output to hierarchical OpenAPI format.

        Unlike translate_openapi which flattens all paths, this preserves
        the router hierarchy while converting entries to OpenAPI format.

        Args:
            nodes_data: Output from nodes() in standard format.
            lazy: If True, child routers are returned as router references.

        Returns:
            Dict with "paths" containing local OpenAPI path items,
            "$defs" containing all type definitions (if any nested types),
            and "routers" containing nested h_openapi structures for children.
        """
        paths: dict[str, Any] = {}
        all_defs: dict[str, Any] = {}

        entries = nodes_data.get("entries", {})
        for entry_name, entry_info in entries.items():
            path = f"/{entry_name}"
            path_item, defs = OpenAPITranslator.entry_info_to_openapi(entry_name, entry_info)
            paths[path] = path_item
            all_defs.update(defs)

        routers_data = nodes_data.get("routers", {})
        routers: dict[str, Any]
        if lazy:
            routers = dict(routers_data)
        else:
            routers = {}
            for child_name, child_data in routers_data.items():
                child_h_openapi = OpenAPITranslator.translate_h_openapi(child_data, lazy=False)
                if child_h_openapi:
                    routers[child_name] = child_h_openapi
                    # Collect $defs from children
                    if "$defs" in child_h_openapi:
                        all_defs.update(child_h_openapi.pop("$defs"))

        result: dict[str, Any] = {
            "description": nodes_data.get("description"),
            "owner_doc": nodes_data.get("owner_doc"),
        }
        if paths:
            result["paths"] = paths
        if all_defs:
            result["$defs"] = all_defs
        if routers:
            result["routers"] = routers
        return result

    @staticmethod
    def entry_info_to_openapi(
        name: str, entry_info: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Convert entry info dict to OpenAPI path item format.

        HTTP method determination priority:
        1. Explicit override via openapi plugin config (openapi_method in metadata)
        2. Guessed from function signature (guess_http_method)

        Returns:
            Tuple of (path_item, defs) where defs contains any $defs extracted
            from schemas (for nested types like TypedDict).
        """
        func = entry_info.get("callable")
        doc = entry_info.get("doc", "")
        summary = doc.split("\n")[0] if doc else name
        metadata = entry_info.get("metadata", {})
        collected_defs: dict[str, Any] = {}

        openapi_config = metadata.get("plugin_config", {}).get("openapi", {})
        explicit_method = openapi_config.get("method")
        if explicit_method:
            http_method = explicit_method.lower()
        elif func:
            http_method = OpenAPITranslator.guess_http_method(func)
        else:
            http_method = "post"

        operation: dict[str, Any] = {
            "operationId": name,
            "summary": summary,
        }
        if doc:
            operation["description"] = doc

        tags = openapi_config.get("tags")
        if tags:
            operation["tags"] = tags if isinstance(tags, list) else [tags]

        pydantic_meta = metadata.get("pydantic", {})
        model = pydantic_meta.get("model")

        if not model and func:
            model = OpenAPITranslator.create_pydantic_model_for_func(func)

        if model and hasattr(model, "model_json_schema"):
            schema = model.model_json_schema()
            # Extract $defs from request body schema
            if "$defs" in schema:
                collected_defs.update(schema.pop("$defs"))
            if http_method == "get":
                parameters = OpenAPITranslator.schema_to_parameters(schema)
                if parameters:
                    operation["parameters"] = parameters
            else:
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": schema}},
                }

        if func:
            try:
                hints = get_type_hints(func)
                return_hint = hints.get("return")
                if return_hint:
                    response_schema = OpenAPITranslator.python_type_to_openapi_schema(
                        return_hint
                    )
                    # Extract $defs from response schema
                    if "$defs" in response_schema:
                        collected_defs.update(response_schema.pop("$defs"))
                    operation["responses"] = {
                        "200": {
                            "description": "Successful response",
                            "content": {"application/json": {"schema": response_schema}},
                        }
                    }
            except Exception:
                pass

        if "responses" not in operation:
            operation["responses"] = {"200": {"description": "Successful response"}}

        return {http_method: operation}, collected_defs

    @staticmethod
    def create_pydantic_model_for_func(func: Callable) -> Any | None:
        """Create a pydantic model from function type hints.

        This is used when the pydantic plugin is not active but we still
        want to extract parameter schema for OpenAPI.

        Args:
            func: The callable to analyze.

        Returns:
            A pydantic model class, or None if no type hints available.
        """
        from pydantic import create_model

        try:
            hints = get_type_hints(func, include_extras=True)
        except Exception:
            return None

        hints.pop("return", None)
        if not hints:
            return None

        sig = inspect.signature(func)
        fields: dict[str, Any] = {}
        for param_name, hint in hints.items():
            param = sig.parameters.get(param_name)
            if param is None:
                continue
            if param.default is inspect.Parameter.empty:
                fields[param_name] = (hint, ...)
            else:
                fields[param_name] = (hint, param.default)

        if not fields:
            return None

        try:
            return create_model(f"{func.__name__}_Model", **fields)
        except Exception:
            return None

    @staticmethod
    def schema_to_parameters(schema: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert pydantic JSON schema to OpenAPI query parameters.

        Args:
            schema: Pydantic model JSON schema.

        Returns:
            List of OpenAPI parameter objects for query string.
        """
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))
        parameters: list[dict[str, Any]] = []

        for prop_name, prop_schema in properties.items():
            param: dict[str, Any] = {
                "name": prop_name,
                "in": "query",
                "required": prop_name in required_fields,
                "schema": prop_schema,
            }
            parameters.append(param)

        return parameters

    @staticmethod
    def python_type_to_openapi_schema(python_type: Any) -> dict[str, Any]:
        """Convert Python type to OpenAPI schema dict using pydantic.

        Uses pydantic's TypeAdapter to generate JSON schema for any type.
        """
        from pydantic import TypeAdapter

        try:
            adapter = TypeAdapter(python_type)
            return adapter.json_schema()
        except Exception:
            return {"type": "object"}

    @staticmethod
    def guess_http_method(func: Callable) -> str:
        """Guess HTTP method from function signature.

        Rules:
        - Default = POST (safer, no caching, no URL exposure)
        - GET only if: no parameters AND returns something (not None)

        Examples:
            def health() -> dict:      # GET - no params, returns data
            def list() -> list:        # GET - no params, returns data
            def add(id: int):          # POST - has params
            def reset():               # POST - no params, no return (side effect)

        Args:
            func: The callable to analyze.

        Returns:
            "get" or "post" based on signature analysis.
        """
        try:
            hints = get_type_hints(func)
        except Exception:
            return "post"

        return_hint = hints.pop("return", None)

        if hints:
            return "post"

        if return_hint is None or return_hint is type(None):
            return "post"

        return "get"
