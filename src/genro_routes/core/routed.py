"""RoutedClass mixin and router proxy for Genro Routes.

The mixin keeps router state off user instances via slots and offers a proxy
for configuration/lookup.

RoutedClass
-----------
A mixin class providing:
    - ``_register_router(router)``: Lazily creates a registry dict on the instance
      and stores the router under ``router.name`` if truthy.
    - ``_iter_registered_routers``: Yields ``(name, router)`` for registry entries.
    - ``routedclass`` property: Returns cached ``_RoutedProxy`` bound to the owner.

_RoutedProxy
------------
Bound to the owning ``RoutedClass`` instance.

Router lookup:
    - ``get_router(name, path=None)`` splits combined specs (``foo.bar``) into
      base router + child path. Raises ``AttributeError`` if no router is found.

Configuration entrypoint:
    - ``configure(target, **options)`` accepts string, dict, or list targets.
    - ``"?"`` shortcut returns ``_describe_all()``.

Example::

    from genro_routes import Router, RoutedClass, route

    class MyService(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def hello(self):
            return "Hello!"

    svc = MyService()
    svc.routedclass.configure("api:logging/_all_", enabled=False)
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from genro_toolbox.typeutils import safe_is_instance

from .base_router import ROUTER_REGISTRY_ATTR_NAME

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .router import Router

__all__ = ["RoutedClass", "is_routed_class"]

_PROXY_ATTR_NAME = "__routed_proxy__"


class RoutedClass:
    """Mixin providing helper proxies for runtime routers.

    Subclass this to enable automatic router registration and configuration
    via the ``routedclass`` property.
    """

    __slots__ = (_PROXY_ATTR_NAME, ROUTER_REGISTRY_ATTR_NAME, "_routed_parent")

    def __setattr__(self, name: str, value: Any) -> None:
        current = self._get_current_routed_attr(name)
        if current is not None:
            self._auto_detach_child(current)

        object.__setattr__(self, name, value)

    def _get_current_routed_attr(self, name: str) -> Any:
        try:
            current = object.__getattribute__(self, name)
        except AttributeError:
            return None
        if not safe_is_instance(current, "genro_routes.core.routed.RoutedClass"):
            return None
        if getattr(current, "_routed_parent", None) is not self:
            return None  # pragma: no cover - only detach if bound to this parent
        return current

    def _auto_detach_child(self, current: Any) -> None:
        registry = getattr(self, ROUTER_REGISTRY_ATTR_NAME, {}) or {}
        import contextlib

        for router in registry.values():
            with contextlib.suppress(Exception):  # best-effort; avoid blocking setattr
                router.detach_instance(current)  # type: ignore[attr-defined]

    def _register_router(self, router: Router) -> None:
        """Register a router with this instance.

        Called automatically by Router during initialization.
        """
        registry = getattr(self, ROUTER_REGISTRY_ATTR_NAME, None)
        if registry is None:
            registry = {}
            setattr(self, ROUTER_REGISTRY_ATTR_NAME, registry)
        if not hasattr(self, "_routed_parent"):
            object.__setattr__(self, "_routed_parent", None)
        if router.name:
            registry[router.name] = router

    def _iter_registered_routers(self):
        """Yield (name, router) pairs for all registered routers."""
        registry = getattr(self, ROUTER_REGISTRY_ATTR_NAME, None) or {}
        yield from registry.items()

    @property
    def routedclass(self) -> _RoutedProxy:
        """Return a proxy for router configuration and lookup."""
        proxy = getattr(self, _PROXY_ATTR_NAME, None)
        if proxy is None:
            proxy = _RoutedProxy(self)
            setattr(self, _PROXY_ATTR_NAME, proxy)
        return proxy


class _RoutedProxy:
    """Proxy for accessing and configuring routers on a RoutedClass instance."""

    _owner: RoutedClass

    def __init__(self, owner: RoutedClass):
        object.__setattr__(self, "_owner", owner)

    def get_router(self, name: str, path: str | None = None):
        """Look up a router by name, optionally navigating a path with '/' separator."""
        owner = self._owner
        base_name, extra_path = self._split_router_spec(name, path)
        router = self._lookup_router(owner, base_name)
        if router is None:
            raise AttributeError(f"No Router named '{base_name}' on {type(owner).__name__}")
        if not extra_path:
            return router
        return self._navigate_router(router, extra_path)

    def _lookup_router(self, owner: RoutedClass, name: str) -> Router | None:
        registry = getattr(owner, ROUTER_REGISTRY_ATTR_NAME, None) or {}
        router = registry.get(name)
        if router:
            return router  # type: ignore[no-any-return]
        candidate = getattr(owner, name, None)
        if safe_is_instance(candidate, "genro_routes.core.base_router.BaseRouter"):
            registry[name] = candidate
            return candidate
        return None

    # Helpers -------------------------------------------------
    def _split_router_spec(self, name: str, path: str | None) -> tuple[str, str | None]:
        extra_path = path
        base_name = name
        if not path and "/" in name:
            base_name, extra_path = name.split("/", 1)
        return base_name, extra_path

    def _navigate_router(self, root, path: str):
        node = root
        for segment in path.split("/"):
            segment = segment.strip()
            if not segment:
                continue
            node = node._children[segment]
        return node

    def _parse_target(self, target: str) -> tuple[str, str, str]:
        if ":" not in target:
            raise ValueError("Target must include router:plugin")
        router_part, rest = target.split(":", 1)
        router_part = router_part.strip()
        if not router_part:
            raise ValueError("Router name cannot be empty")
        if "/" in rest:
            plugin_part, selector = rest.split("/", 1)
        else:
            plugin_part, selector = rest, "_all_"
        plugin_part = plugin_part.strip()
        selector = selector.strip() or "_all_"
        if not plugin_part:
            raise ValueError("Plugin name cannot be empty")
        return router_part, plugin_part, selector

    def _match_handlers(self, router, selector: str) -> set[str]:
        names = list(router._entries.keys())
        patterns = [token.strip() for token in selector.split(",") if token.strip()]
        matched: set[str] = set()
        for pattern in patterns:
            for handler_name in names:
                if fnmatchcase(handler_name, pattern):
                    matched.add(handler_name)
        return matched

    def _apply_config(self, plugin: Any, target: str, options: dict[str, Any]) -> None:
        plugin.configure(_target=target, **options)

    def _describe_all(self) -> dict[str, Any]:
        owner = self._owner
        result: dict[str, Any] = {}
        registry = getattr(owner, ROUTER_REGISTRY_ATTR_NAME, None) or {}
        for attr_name, router in registry.items():
            result[attr_name] = self._describe_router(router)
        return result

    def _describe_router(self, router) -> dict[str, Any]:
        return {
            "name": router.name,
            "plugins": [
                {
                    "name": plugin.name,
                    "description": getattr(plugin, "description", ""),
                    "config": plugin.configuration(),
                    "overrides": {
                        handler: plugin.configuration(handler) for handler in router._entries
                    },
                }
                for plugin in router.iter_plugins()
            ],
            "entries": list(router._entries.keys()),
            "routers": {
                child_name: self._describe_router(child)
                for child_name, child in router._children.items()
            },
        }

    def configure(self, target: Any, **options: Any):
        """Configure router plugins.

        Args:
            target: Configuration target. Can be:
                - ``"?"`` to describe all routers
                - ``"router:plugin"`` for global plugin config
                - ``"router:plugin/selector"`` for handler-specific config
                - A dict with ``"target"`` key and options
                - A list of targets
            **options: Configuration options for the plugin.

        Returns:
            Configuration result dict or description.
        """
        if isinstance(target, (list, tuple)):
            if options:
                raise ValueError("Do not mix shared kwargs with list targets")
            return [self.configure(entry) for entry in target]
        if isinstance(target, dict):
            entry = dict(target)
            try:
                entry_target = entry.pop("target")
            except KeyError as err:
                raise ValueError("Dict targets must include 'target'") from err
            return self.configure(entry_target, **entry)
        if not isinstance(target, str):
            raise TypeError("Target must be a string, dict, or list")
        target = target.strip()
        if target == "?":
            if options:
                raise ValueError("Options are not allowed with '?' ")
            return self._describe_all()
        router_spec, plugin_name, selector = self._parse_target(target)
        bound_router = self.get_router(router_spec)
        plugin = getattr(bound_router, plugin_name, None)
        if plugin is None:
            raise AttributeError(f"No plugin named '{plugin_name}' on router '{router_spec}'")
        if not options:
            raise ValueError("No configuration options provided")
        selector = selector or "_all_"
        if selector.lower() == "_all_":
            self._apply_config(plugin, "_all_", options)
            return {"target": target, "updated": ["_all_"]}
        matches = self._match_handlers(bound_router, selector)
        if not matches:
            raise KeyError(f"No handlers matching '{selector}' on router '{router_spec}'")
        for handler in matches:
            self._apply_config(plugin, handler, options)
        return {"target": target, "updated": sorted(matches)}


def is_routed_class(obj: Any) -> bool:
    """Return True when ``obj`` is a RoutedClass instance."""
    return safe_is_instance(obj, "genro_routes.core.routed.RoutedClass")  # type: ignore[no-any-return]
