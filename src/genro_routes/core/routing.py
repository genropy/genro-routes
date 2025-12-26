"""RoutingClass mixin and router proxy for Genro Routes.

The mixin keeps router state off user instances via slots and offers a proxy
for configuration/lookup.

RoutingClass
------------
A mixin class providing:
    - ``_register_router(router)``: Lazily creates a registry dict on the instance
      and stores the router under ``router.name`` if truthy.
    - ``_iter_registered_routers``: Yields ``(name, router)`` for registry entries.
    - ``routing`` property: Returns cached ``_RoutingProxy`` bound to the owner.

_RoutingProxy
-------------
Bound to the owning ``RoutingClass`` instance.

Router lookup:
    - ``get_router(name, path=None)`` splits combined specs (``foo/bar``) into
      base router + child path. Raises ``AttributeError`` if no router is found.

Configuration entrypoint:
    - ``configure(target, **options)`` accepts string, dict, or list targets.
    - ``"?"`` shortcut returns ``_describe_all()``.

Example::

    from genro_routes import Router, RoutingClass, route

    class MyService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def hello(self):
            return "Hello!"

    svc = MyService()
    svc.routing.configure("api:logging/_all_", enabled=False)
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from genro_toolbox.typeutils import safe_is_instance

from .context import RoutingContext

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .router import Router

__all__ = ["RoutingClass", "is_routing_class"]

_PROXY_ATTR_NAME = "__routing_proxy__"


class RoutingClass:
    """Mixin providing helper proxies for runtime routers.

    Subclass this to enable automatic router registration and configuration
    via the ``routing`` property.
    """

    __slots__ = (
        _PROXY_ATTR_NAME,
        "__genro_routes_router_registry__",
        "_routing_parent",
        "_context",
        "_capabilities",
    )

    def __setattr__(self, name: str, value: Any) -> None:
        current = self._get_current_routing_attr(name)
        if current is not None:
            self._auto_detach_child(current)

        object.__setattr__(self, name, value)

    def _get_current_routing_attr(self, name: str) -> Any:
        try:
            current = object.__getattribute__(self, name)
        except AttributeError:
            return None
        if not safe_is_instance(current, "genro_routes.core.routing.RoutingClass"):
            return None
        if getattr(current, "_routing_parent", None) is not self:
            return None  # pragma: no cover - only detach if bound to this parent
        return current

    @property
    def _routers(self) -> dict:
        """Lazy-initialized router registry."""
        registry = getattr(self, "__genro_routes_router_registry__", None)
        if registry is None:
            registry = {}
            self.__genro_routes_router_registry__ = registry
        return registry

    @_routers.setter
    def _routers(self, value: dict) -> None:
        self.__genro_routes_router_registry__ = value

    def _auto_detach_child(self, current: Any) -> None:
        import contextlib

        for router in self._routers.values():
            with contextlib.suppress(Exception):  # best-effort; avoid blocking setattr
                router.detach_instance(current)  # type: ignore[attr-defined]

    def _register_router(self, router: Router) -> None:
        """Register a router with this instance.

        Called automatically by Router during initialization.
        """
        if not hasattr(self, "_routing_parent"):
            object.__setattr__(self, "_routing_parent", None)
        if router.name:
            self._routers[router.name] = router

    def _iter_registered_routers(self):
        """Yield (name, router) pairs for all registered routers."""
        yield from self._routers.items()

    @property
    def routing(self) -> _RoutingProxy:
        """Return a proxy for router configuration and lookup."""
        proxy = getattr(self, _PROXY_ATTR_NAME, None)
        if proxy is None:
            proxy = _RoutingProxy(self)
            setattr(self, _PROXY_ATTR_NAME, proxy)
        return proxy

    @property
    def context(self) -> RoutingContext | None:
        """Return the execution context, searching up the parent chain.

        The context is set by the adapter (ASGI, Telegram, etc.) on the root
        RoutingClass instance and propagates automatically to children.

        Returns:
            The current RoutingContext or None if not set.
        """
        ctx: RoutingContext | None = getattr(self, "_context", None)
        if ctx is not None:
            return ctx
        # Propagate from parent if not set locally
        parent: RoutingClass | None = getattr(self, "_routing_parent", None)
        if parent is not None:
            return parent.context
        return None

    @context.setter
    def context(self, value: RoutingContext | None) -> None:
        """Set the execution context.

        Args:
            value: A RoutingContext instance or None.

        Raises:
            TypeError: If value is not a RoutingContext or None.
        """
        if value is not None and not isinstance(value, RoutingContext):
            raise TypeError("context must be a RoutingContext instance")
        object.__setattr__(self, "_context", value)

    @property
    def default_router(self) -> Any:
        """Return the default router for this instance.

        Returns the router only if exactly one router is registered.
        This allows ``@route()`` without arguments to work when there's
        an unambiguous single router.

        If multiple routers are registered, returns None and ``@route()``
        requires an explicit router name argument.

        Returns:
            Router | None: The single router or None if zero or multiple.
        """
        routers = self._routers
        if len(routers) == 1:
            return next(iter(routers.values()))
        return None

    @property
    def capabilities(self):
        """Return the capabilities declared by this instance.

        Capabilities represent what features/dependencies this service has
        available at runtime. Used by EnvPlugin to filter entries based
        on capability requirements.

        Capabilities must be a ``CapabilitiesSet`` subclass instance. Each
        capability is defined as a method decorated with ``@capability``
        that returns ``True`` if the capability is currently available.

        Returns:
            A CapabilitiesSet instance, or empty set if not configured.

        Example::

            from genro_routes.plugins.env import CapabilitiesSet, capability

            class PaymentCapabilities(CapabilitiesSet):
                def __init__(self, service):
                    self._service = service

                @capability
                def stripe(self) -> bool:
                    return self._service._stripe_configured

                @capability
                def paypal(self) -> bool:
                    return self._service._paypal_configured

            class PaymentService(RoutingClass):
                def __init__(self):
                    self.api = Router(self, name="api").plug("env")
                    self._stripe_configured = True
                    self._paypal_configured = False
                    self.capabilities = PaymentCapabilities(self)
        """
        return getattr(self, "_capabilities", None) or set()

    @capabilities.setter
    def capabilities(self, value) -> None:
        """Set the capabilities for this instance.

        Args:
            value: A CapabilitiesSet instance for dynamic capability evaluation.

        Raises:
            TypeError: If value is not a CapabilitiesSet.
        """
        # Import here to avoid circular imports
        from genro_routes.plugins.env import CapabilitiesSet

        if not isinstance(value, CapabilitiesSet):
            raise TypeError(f"capabilities must be a CapabilitiesSet instance, got {type(value).__name__}")
        object.__setattr__(self, "_capabilities", value)


class _RoutingProxy:
    """Proxy for accessing and configuring routers on a RoutingClass instance."""

    _owner: RoutingClass

    def __init__(self, owner: RoutingClass):
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

    def _lookup_router(self, owner: RoutingClass, name: str) -> Router | None:
        router = owner._routers.get(name)
        if router:
            return router  # type: ignore[no-any-return]
        candidate = getattr(owner, name, None)
        if safe_is_instance(candidate, "genro_routes.core.base_router.BaseRouter"):
            owner._routers[name] = candidate
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
        for attr_name, router in owner._routers.items():
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


def is_routing_class(obj: Any) -> bool:
    """Return True when ``obj`` is a RoutingClass instance."""
    return safe_is_instance(obj, "genro_routes.core.routing.RoutingClass")  # type: ignore[no-any-return]
