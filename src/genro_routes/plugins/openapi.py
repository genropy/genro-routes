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

        # Method will be guessed as GET (scalar params only)
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

from typing import Any

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
