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

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .context import RoutingContext
    from .router import Router

__all__ = ["RoutingClass", "ResultWrapper", "is_routing_class", "is_result_wrapper"]


class ResultWrapper:
    """Wrapper for handler results with additional metadata.

    Allows handlers to return results with metadata (e.g., mime_type)
    that the dispatcher can use when building the response.

    Usage in handlers:
        return self.result_wrapper(content, mime_type="text/html")
    """

    __slots__ = ("value", "metadata")

    def __init__(self, value: Any, metadata: dict[str, Any]) -> None:
        self.value = value
        self.metadata = metadata

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
        "_ctx",
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
    def ctx(self) -> RoutingContext | None:
        """Return the execution context, walking up the parent chain."""
        result: RoutingContext | None = getattr(self, "_ctx", None)
        if result is not None:
            return result
        parent: RoutingClass | None = getattr(self, "_routing_parent", None)
        if parent is not None:
            return parent.ctx
        return None

    @ctx.setter
    def ctx(self, value: RoutingContext | None) -> None:
        """Set the execution context on this instance."""
        object.__setattr__(self, "_ctx", value)

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

    def result_wrapper(self, value: Any, **metadata: Any) -> ResultWrapper:
        """Wrap a handler result with metadata.

        Use this when a handler needs to return additional metadata
        (e.g., mime_type) along with the result value.

        Args:
            value: The actual result to return.
            **metadata: Key-value pairs of metadata (e.g., mime_type="text/html").

        Returns:
            A ResultWrapper instance containing value and metadata.

        Example:
            @route("root")
            def _resource(self, name: str):
                content, mime_type = self.load_resource(name)
                return self.result_wrapper(content, mime_type=mime_type)
        """
        return ResultWrapper(value, metadata)


class _RoutingProxy:
    """Proxy for accessing and configuring routers on a RoutingClass instance.

    Provides a unified interface for router lookup and plugin configuration.
    Access via the ``routing`` property on any RoutingClass instance.

    Main operations:
        - ``get_router(name)``: Look up a router by name
        - ``configure(target, **options)``: Configure plugin settings
        - ``attach_instance(child)``: Attach child RoutingClass instances

    Target syntax for configure():
        - ``"router:plugin"`` - Global plugin config
        - ``"router:plugin/handler"`` - Per-handler config
        - ``"router:plugin/pattern*"`` - Glob pattern matching
        - ``"?"`` - Describe all routers and their configuration

    Example:
        >>> svc.routing.configure("api:logging", before=False)
        >>> svc.routing.configure("api:auth/admin_*", rule="admin")
        >>> svc.routing.configure("?")  # introspection
    """

    _owner: RoutingClass

    def __init__(self, owner: RoutingClass):
        object.__setattr__(self, "_owner", owner)

    def get_router(self, name: str, path: str | None = None):
        """Look up a router by name, optionally navigating child routers.

        Args:
            name: Router name, or "name/child/grandchild" path notation.
            path: Optional additional path to navigate after finding router.

        Returns:
            The resolved Router (or child router if path provided).

        Raises:
            AttributeError: If no router with that name exists.
            KeyError: If child path navigation fails.

        Example:
            >>> svc.routing.get_router("api")
            >>> svc.routing.get_router("api/users")  # child router
            >>> svc.routing.get_router("api", "users/detail")
        """
        owner = self._owner
        base_name, extra_path = self._split_router_spec(name, path)
        router = self._lookup_router(owner, base_name)
        if router is None:
            raise AttributeError(f"No Router named '{base_name}' on {type(owner).__name__}")
        if not extra_path:
            return router
        return self._navigate_router(router, extra_path)

    def instance(self, path: str) -> RoutingClass:
        """Return the RoutingClass instance that owns the child router at path.

        Args:
            path: Router path in "router/child" or "router/child/grandchild" notation.

        Returns:
            The RoutingClass instance owning the resolved child router.

        Raises:
            AttributeError: If the base router is not found.
            KeyError: If child path navigation fails.

        Example:
            >>> svc.routing.instance("api/users")  # → UsersModule instance
            >>> svc.routing.instance("api/users/detail")  # → nested child instance
        """
        router = self.get_router(path)
        return router.instance  # type: ignore[no-any-return]

    def _lookup_router(self, owner: RoutingClass, name: str) -> Router | None:
        """Find a router by name in the owner's registry or as attribute."""
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
        """Split 'router/path' into (router, path) components."""
        extra_path = path
        base_name = name
        if not path and "/" in name:
            base_name, extra_path = name.split("/", 1)
        return base_name, extra_path

    def _navigate_router(self, root, path: str):
        """Walk child routers following the path segments."""
        node = root
        for segment in path.split("/"):
            segment = segment.strip()
            if not segment:
                continue
            node = node._children[segment]
        return node

    def _parse_target(self, target: str) -> tuple[str, str, str]:
        """Parse 'router:plugin/selector' into (router, plugin, selector)."""
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
        """Match handler names against glob patterns (comma-separated)."""
        names = list(router._entries.keys())
        patterns = [token.strip() for token in selector.split(",") if token.strip()]
        matched: set[str] = set()
        for pattern in patterns:
            for handler_name in names:
                if fnmatchcase(handler_name, pattern):
                    matched.add(handler_name)
        return matched

    def _describe_all(self) -> dict[str, Any]:
        """Build introspection dict for all routers on the owner."""
        owner = self._owner
        result: dict[str, Any] = {}
        for attr_name, router in owner._routers.items():
            result[attr_name] = self._describe_router(router)
        return result

    def _describe_router(self, router) -> dict[str, Any]:
        """Build introspection dict for a single router."""
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

    def attach_instance(
        self,
        instance: RoutingClass,
        name: str | None = None,
        mapping: str | None = None,
        router_name: str | None = None,
    ):
        """Attach a child instance to a router.

        Convenience method that delegates to a router's attach_instance.
        Uses the default router unless router_name is specified.

        Args:
            instance: The RoutingClass instance to attach.
            name: Alias for the child's router.
            mapping: Explicit mapping for children with multiple routers.
            router_name: Optional router name to attach to. If not provided, uses
                the default router (only works if exactly one router exists).

        Returns:
            The result of router.attach_instance().

        Raises:
            RuntimeError: If no default router exists and router_name not specified.
            AttributeError: If router_name doesn't match any registered router.
        """
        if router_name is not None:
            router = self._lookup_router(self._owner, router_name)
            if router is None:
                raise AttributeError(
                    f"No router named '{router_name}' on {type(self._owner).__name__}"
                )
        else:
            router = self._owner.default_router
            if router is None:
                count = len(self._owner._routers)
                raise RuntimeError(
                    f"attach_instance requires exactly one router; "
                    f"{type(self._owner).__name__} has {count}"
                )
        return router.attach_instance(instance, name=name, mapping=mapping)

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
            plugin.configure(_target="_all_", **options)
            return {"target": target, "updated": ["_all_"]}
        matches = self._match_handlers(bound_router, selector)
        if not matches:
            raise KeyError(f"No handlers matching '{selector}' on router '{router_spec}'")
        for handler in matches:
            plugin.configure(_target=handler, **options)
        return {"target": target, "updated": sorted(matches)}


def is_routing_class(obj: Any) -> bool:
    """Return True when ``obj`` is a RoutingClass instance."""
    return safe_is_instance(obj, "genro_routes.core.routing.RoutingClass")  # type: ignore[no-any-return]


def is_result_wrapper(obj: Any) -> bool:
    """Return True when ``obj`` is a ResultWrapper instance."""
    return isinstance(obj, ResultWrapper)
