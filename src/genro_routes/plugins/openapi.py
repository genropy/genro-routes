"""OpenAPI plugin for Genro Routes.

Provides explicit control over OpenAPI schema generation for handlers.
Use this plugin to override automatically guessed HTTP methods or add
OpenAPI-specific metadata like tags, summary, description, and security.

Configuration
-------------
Accepted keys (router-level or per-handler):
    - ``enabled``: Gate the plugin entirely (default True)
    - ``method``: HTTP method override (e.g., "get", "post", "delete")
    - ``tags``: OpenAPI tags (string or list of strings)
    - ``summary``: Summary override for the operation
    - ``description``: Description override for the operation
    - ``deprecated``: Mark the operation as deprecated (default False)
    - ``security_scheme``: Security scheme name (default "BearerAuth")
    - ``security``: Explicit security override (list, or [] for public)

Cross-plugin integration:
    - When pydantic plugin is active, uses pre-computed ``response_schema`` from
      metadata. Falls back to direct ``get_type_hints`` extraction otherwise.
    - When auth plugin is active, ``security`` is auto-derived from ``auth_rule``.
    - When env plugin is active, ``x-requires`` is auto-derived from ``env_requires``.

Example::

    from genro_routes import Router, RoutingClass, route

    class MyService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("openapi").plug("auth")

        @route("api", openapi_method="delete")
        def delete_item(self, item_id: int) -> dict:
            return {"deleted": item_id}

        @route("api", openapi_tags=["users"], openapi_deprecated=True)
        def old_list(self) -> list:
            return []

        @route("api", auth_rule="admin")
        def admin_only(self) -> dict:
            return {}

        @route("api", openapi_security=[])
        def force_public(self) -> dict:
            return {}
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

from genro_routes.core.router import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class OpenAPIPlugin(BasePlugin):
    """OpenAPI plugin for explicit schema control.

    Provides explicit control over OpenAPI schema generation. By default,
    HTTP methods are guessed from function signatures (GET for scalar params,
    POST for complex types). Use this plugin to override the guessed method
    or add OpenAPI-specific metadata.

    Configuration options:
        - ``enabled``: Enable/disable the plugin (default True)
        - ``method``: HTTP method override ("get", "post", "put", "delete", "patch")
        - ``tags``: OpenAPI tags for grouping (string or list of strings)
        - ``summary``: Summary text override for the operation
        - ``description``: Description override for the operation
        - ``deprecated``: Mark the operation as deprecated (default False)
        - ``security_scheme``: Security scheme name (default "BearerAuth")
        - ``security``: Explicit per-operation security override (list or [])

    Cross-plugin integration:
        - Auth plugin: ``auth_rule`` auto-generates ``security`` field.
        - Env plugin: ``env_requires`` auto-generates ``x-requires`` extension.

    Method guessing rules (when not overridden):
        - GET: All parameters are scalar types (str, int, float, bool, Enum)
        - POST: Any parameter is complex (dict, list, TypedDict, Pydantic model)

    Attributes:
        plugin_code: "openapi" - used for registration and config prefix.
        plugin_description: Human-readable description.

    Example:
        Override HTTP method::

            @route("api", openapi_method="delete")
            def remove_item(self, item_id: int) -> dict:
                return {"deleted": item_id}

        Add tags and mark deprecated::

            @route("api", openapi_tags=["users", "admin"], openapi_deprecated=True)
            def old_list_users(self) -> list:
                return []

        Retrieve OpenAPI info::

            node = router.node("remove_item", openapi=True)
            print(node.openapi)  # {"delete": {"operationId": "remove_item", ...}}
    """

    plugin_code = "openapi"
    plugin_description = "Provides explicit control over OpenAPI schema generation"

    def configure(  # type: ignore[override]
        self,
        enabled: bool = True,
        method: str | None = None,
        tags: str | list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        deprecated: bool = False,
        security_scheme: str = "BearerAuth",
        security: list | None = None,
    ):
        """Configure OpenAPI plugin options.

        Args:
            enabled: Enable/disable the plugin entirely.
            method: HTTP method override (get, post, put, delete, patch).
            tags: OpenAPI tags for grouping operations.
            summary: Summary text override for the operation.
            description: Description override for the operation.
            deprecated: Mark the operation as deprecated.
            security_scheme: Name of the security scheme for auth-based
                security derivation (default "BearerAuth").
            security: Explicit security override for the operation.
                Use [] to force public, or [{"OAuth2": ["read"]}] for custom.
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
        if cfg.get("description"):
            metadata["description"] = cfg["description"]
        if cfg.get("deprecated"):
            metadata["deprecated"] = cfg["deprecated"]
        if cfg.get("security_scheme") and cfg["security_scheme"] != "BearerAuth":
            metadata["security_scheme"] = cfg["security_scheme"]
        if cfg.get("security") is not None:
            metadata["security"] = cfg["security"]

        return {"openapi": metadata} if metadata else {}


Router.register_plugin(OpenAPIPlugin)


class OpenAPITranslator:
    """Translator for converting router nodes to OpenAPI format.

    This class provides static methods to translate the output of
    ``router.nodes()`` to OpenAPI-compatible formats.

    Modes for nodes():
        - ``openapi``: Flat format with all paths merged into a single paths dict.
        - ``h_openapi``: Hierarchical format preserving the router tree structure.

    For single entry info:
        - ``entry_to_openapi(entry)``: Convert a MethodEntry to OpenAPI path item.
          Used by ``router.node(path, openapi=True)`` to populate the ``openapi``
          attribute on the returned RouterNode.

    Example::

        node = router.node("my_handler", openapi=True)
        print(node.openapi)  # {"get": {"operationId": "my_handler", ...}}
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
        path_prefix: str = "",
    ) -> dict[str, Any]:
        """Translate nodes() output to hierarchical OpenAPI format.

        Unlike translate_openapi which flattens all paths, this preserves
        the router hierarchy while converting entries to OpenAPI format.

        Args:
            nodes_data: Output from nodes() in standard format.
            lazy: If True, child routers are returned as router references.
            path_prefix: Prefix for generated paths (used when called with basepath).

        Returns:
            Dict with "paths" containing local OpenAPI path items,
            "$defs" containing all type definitions (if any nested types),
            and "routers" containing nested h_openapi structures for children.
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

        # Apply summary override from openapi plugin config
        if openapi_config.get("summary"):
            summary = openapi_config["summary"]

        operation: dict[str, Any] = {
            "operationId": name,
            "summary": summary,
        }
        # Apply description override from openapi plugin config, fallback to docstring
        if openapi_config.get("description"):
            operation["description"] = openapi_config["description"]
        elif doc:
            operation["description"] = doc

        if openapi_config.get("deprecated"):
            operation["deprecated"] = True

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

        # Response schema: prefer pre-computed from pydantic plugin, fallback to direct extraction
        response_schema = None
        pre_computed = pydantic_meta.get("response_schema")
        if pre_computed is not None:
            response_schema = pre_computed.copy()
        elif func:
            try:
                func_hints = get_type_hints(func)
                return_hint = func_hints.get("return")
                if return_hint:
                    response_schema = OpenAPITranslator.python_type_to_openapi_schema(
                        return_hint
                    )
            except Exception:
                pass

        if response_schema is not None:
            if "$defs" in response_schema:
                collected_defs.update(response_schema.pop("$defs"))
            operation["responses"] = {
                "200": {
                    "description": "Successful response",
                    "content": {"application/json": {"schema": response_schema}},
                }
            }

        if "responses" not in operation:
            operation["responses"] = {"200": {"description": "Successful response"}}

        # Security: explicit override takes precedence over auth-derived
        plugins = entry_info.get("plugins", {})
        explicit_security = openapi_config.get("security")
        if explicit_security is not None:
            operation["security"] = explicit_security
        else:
            auth_plugin = plugins.get("auth")
            if auth_plugin is not None:
                auth_config = auth_plugin.get("config", {})
                auth_rule = auth_config.get("rule", "")
                security_scheme = openapi_config.get("security_scheme", "BearerAuth")
                if auth_rule:
                    operation["security"] = [{security_scheme: []}]
                else:
                    operation["security"] = []

        # Derive x-requires from env plugin config
        env_plugin = plugins.get("env")
        if env_plugin is not None:
            env_config = env_plugin.get("config", {})
            env_requires = env_config.get("requires", "")
            if env_requires:
                operation["x-requires"] = env_requires

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

    # Scalar types that can be serialized as query string parameters
    SCALAR_TYPES: set[type] = {str, int, float, bool, type(None)}

    @staticmethod
    def _is_scalar_type(hint: Any) -> bool:
        """Check if a type hint represents a scalar (GET-friendly) type.

        Scalar types can be serialized as query string parameters.
        Complex types (dict, list, models) require POST body.
        """
        # Direct scalar types
        if hint in OpenAPITranslator.SCALAR_TYPES:
            return True

        # Enum subclasses are scalar (serializable as string)
        if isinstance(hint, type) and issubclass(hint, Enum):
            return True

        # Handle Optional[X] and Union types
        origin = get_origin(hint)
        if origin is Union:
            args = get_args(hint)
            # All union members must be scalar
            return all(OpenAPITranslator._is_scalar_type(arg) for arg in args)

        # Any other type (dict, list, TypedDict, Pydantic, classes) is complex
        return False

    @staticmethod
    def guess_http_method(func: Callable) -> str:
        """Guess HTTP method from function signature.

        Rules:
        - GET if all parameters are scalar types (str, int, float, bool, Enum)
        - POST if any parameter is complex (dict, list, TypedDict, models)
        - POST on error (safer fallback)

        Scalar types can be serialized as query string parameters.
        Complex types require a request body.

        Examples:
            def health() -> dict:              # GET - no params
            def get_user(id: int) -> dict:     # GET - scalar param
            def search(q: str, limit: int):    # GET - all scalars
            def create(data: dict):            # POST - complex param
            def update(user: UserModel):       # POST - model param

        Args:
            func: The callable to analyze.

        Returns:
            "get" or "post" based on signature analysis.
        """
        try:
            hints = get_type_hints(func)
        except Exception:
            return "post"

        # Remove return type, we only care about parameters
        hints.pop("return", None)

        # Check if all parameter types are scalar
        for param_type in hints.values():
            if not OpenAPITranslator._is_scalar_type(param_type):
                return "post"

        return "get"

    @staticmethod
    def entry_to_openapi(entry: MethodEntry) -> dict[str, Any]:
        """Convert a MethodEntry to OpenAPI format.

        This is a convenience method for use with router.node(openapi=True).

        Args:
            entry: The MethodEntry to convert.

        Returns:
            Dict with the OpenAPI path item (e.g., {"get": {...}} or {"post": {...}}).
        """
        entry_info: dict[str, Any] = {
            "callable": entry.func,
            "doc": inspect.getdoc(entry.func) or entry.func.__doc__ or "",
            "metadata": entry.metadata,
        }
        path_item, _defs = OpenAPITranslator.entry_info_to_openapi(entry.name, entry_info)
        return path_item
