"""RoutingClass mixin and router proxy for Genro Routes.

One class, one router: every ``RoutingClass`` owns exactly one ``Router``,
exposed as the lazy read-only property ``route``. The router is created on
first access and stored in a slot; users never call ``Router(...)`` directly.
Grouping and hierarchy are expressed by composing RoutingClass instances.

RoutingClass
------------
A mixin class providing:
    - ``route`` property: the instance's Router, created lazily on first
      access. Assigning to it raises ``AttributeError`` (read-only).
    - ``add_branches(specs)``: declare child subrouters as factory specs
      (see Branches below). Accepts one dict, a list of dicts, or a generator.
    - ``remove_branch(name)``: drop a declared branch; if already materialized,
      detach its router.
    - ``branches`` property: read-only view of the declared branch specs.
    - ``routing`` property: cached ``_RoutingProxy`` for configuration/lookup.
    - ``ctx`` property: execution context, walking up the parent chain.
    - ``capabilities`` property: CapabilitiesSet for runtime feature flags.

Branches (declarative, factory-based subrouters)
------------------------------------------------
A branch is a child subrouter declared as a **factory spec** and materialized
(constructed) only when needed. This lets trees with thousands of leaves start
cheaply — nothing is instantiated until walked.

A branch spec is a self-describing dict::

    {"name": "beta", "lazy": True, "cls": Beta, "params": {"x": 56}}

    name   -- alias under which the child is reachable (path segment)
    lazy   -- True: materialize on first traversal; False (eager): materialize
              at first tree access
    cls    -- the RoutingClass subclass to instantiate
    params -- kwargs applied as cls(**params) at materialization

``add_branches`` populates the router's ``_branches`` dict; no instance is
constructed at declaration time. Materialization is the single point where an
instance is built: construct ``cls(**params)``, set ``_routing_parent``, link
into ``_children`` (which triggers plugin inheritance), then drop the spec from
``_branches``. Two timing policies share this one mechanism:

    - eager  -- all eager branches materialize at first tree access
                (idempotent guard on the router: runs once)
    - lazy   -- a lazy branch materializes on-demand when a path first
                traverses its segment

Two distinct laziness levels must not be conflated:

    - spec enumeration happens at the ``add_branches`` call (a generator is
      consumed immediately). Light metadata only.
    - instance construction happens at materialization. This is the real saving.

Introspection (``nodes()``) describes a non-materialized lazy branch WITHOUT
building it, including the class-declared ``@route`` leaves read from the class
(no instance). Reverse lookup (``node("@endpoint_id")``) searches only eager and
already-materialized branches; it skips non-materialized lazy branches.

Sharing a handler across paths is NOT a framework feature: it is an ordinary
route method that reuses another node's callable (its own plugins, child's
callable). Reusing a lazy branch's callable forces that branch's materialization.

Router configuration happens on the existing router in ``__init__`` (binding
is lazy, so this is race-free)::

    class MyService(RoutingClass):
        def __init__(self):
            self.route.description = "My service API"
            self.route.plug("logging")

        @route()
        def hello(self):
            return "Hello!"

Section
-------
Minimal concrete RoutingClass used as a grouping node. A Section carries an
empty router; children are attached under it to build intermediate levels of
a routing tree (including dynamically discovered trees)::

    svc.attach_instance(Section("Admin area"), name="admin")

_RoutingProxy
-------------
Bound to the owning ``RoutingClass`` instance.

Router navigation and introspection use the router's own ``node(path)`` (to
resolve/execute) and ``nodes(basepath=...)`` (to inspect and open a subtree,
materializing lazy branches on the way).

Configuration entrypoint:
    - ``configure(target, **options)`` accepts string, dict, or list targets.
      String targets are ``"plugin"`` or ``"plugin/selector"`` where selector
      is a handler name or comma-separated glob patterns.
    - ``"?"`` shortcut returns the router description dict.
    - Child routers belong to child instances: configure them through the
      child's own ``routing`` proxy.

Example::

    from genro_routes import RoutingClass, route

    class MyService(RoutingClass):
        def __init__(self):
            self.route.plug("logging")

        @route()
        def hello(self):
            return "Hello!"

    svc = MyService()
    svc.routing.configure("logging/_all_", enabled=False)
"""

from __future__ import annotations

import contextlib
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from genro_toolbox.typeutils import safe_is_instance

from .router import Router

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .context import RoutingContext

__all__ = ["RoutingClass", "Section", "ResultWrapper", "is_routing_class", "is_result_wrapper"]


class ResultWrapper:
    """Wrapper for handler results with additional metadata.

    Allows handlers to return results with metadata (e.g., media_type)
    that the dispatcher can use when building the response.

    Usage in handlers:
        return self.result_wrapper(content, media_type="text/html")
    """

    __slots__ = ("value", "metadata")

    def __init__(self, value: Any, metadata: dict[str, Any]) -> None:
        self.value = value
        self.metadata = metadata

_PROXY_ATTR_NAME = "__routing_proxy__"
_ROUTER_ATTR_NAME = "__genro_routes_router__"


class RoutingClass:
    """Mixin binding the instance to its single router.

    Subclass this to get the ``route`` router (created lazily) and the
    ``routing`` configuration proxy.
    """

    __slots__ = (
        _PROXY_ATTR_NAME,
        _ROUTER_ATTR_NAME,
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

    def _auto_detach_child(self, current: Any) -> None:
        router = getattr(self, _ROUTER_ATTR_NAME, None)
        if router is not None:
            with contextlib.suppress(Exception):  # best-effort; avoid blocking setattr
                router.detach_instance(current)

    @property
    def route(self) -> Router:
        """Return the instance's router, creating it on first access."""
        router = getattr(self, _ROUTER_ATTR_NAME, None)
        if router is None:
            router = Router(self)
        return router

    def add_branches(self, specs: Any) -> None:
        """Declare child branches (factory specs) on this instance's router.

        Accepts one spec dict, a list of dicts, or a generator. Each spec is
        ``{"name", "lazy", "cls", "params"}``. Delegates to the router; nothing
        is constructed until materialization (see the Branches section above).
        """
        self.route.add_branches(specs)

    def remove_branch(self, name: str) -> None:
        """Remove a declared branch; detach its child if already materialized."""
        self.route.remove_branch(name)

    @property
    def branches(self) -> dict[str, dict[str, Any]]:
        """Read-only view of declared (not-yet-materialized) branch specs."""
        return self.route.branches

    def _register_router(self, router: Router) -> None:
        """Register the router with this instance.

        Called automatically by Router during initialization. Raises
        ValueError if a different router is already registered.
        """
        if not hasattr(self, "_routing_parent"):
            object.__setattr__(self, "_routing_parent", None)
        existing = getattr(self, _ROUTER_ATTR_NAME, None)
        if existing is not None and existing is not router:
            raise ValueError(f"{type(self).__name__} already has a router")
        object.__setattr__(self, _ROUTER_ATTR_NAME, router)

    def attach_instance(self, child: RoutingClass, *, name: str | None = None) -> None:
        """Attach a child RoutingClass instance.

        Sets ``child._routing_parent = self``. When ``name`` is given,
        ``child.route`` is linked into ``self.route`` under that alias
        (plugin inheritance is triggered by the link).

        Args:
            child: The RoutingClass instance to attach.
            name: Alias under which the child's router is reachable from
                this instance's router. If omitted, only the parent
                relationship is set (no routing link).

        Raises:
            TypeError: If child is not a RoutingClass instance.
            ValueError: If child is already bound to another parent.
            ValueError: If the alias collides with an existing child.

        Example::

            self.attach_instance(child, name="sales")
        """
        if not safe_is_instance(child, "genro_routes.core.routing.RoutingClass"):
            raise TypeError("attach_instance() requires a RoutingClass instance")
        existing_parent = getattr(child, "_routing_parent", None)
        if existing_parent is not None and existing_parent is not self:
            raise ValueError("attach_instance() rejected: child already bound to another parent")

        if name is not None:
            self.route.include(child.route, name=name)

        if getattr(child, "_routing_parent", None) is not self:
            object.__setattr__(child, "_routing_parent", self)

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
                    self.route.plug("env")
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
            @route()
            def _resource(self, name: str):
                content, mime_type = self.load_resource(name)
                return self.result_wrapper(content, mime_type=mime_type)
        """
        return ResultWrapper(value, metadata)


class Section(RoutingClass):
    """Empty routing node for grouping children.

    Use a Section to build intermediate levels of a routing tree without
    defining a dedicated class — e.g. namespacing or dynamically discovered
    hierarchies::

        svc.attach_instance(Section("Admin area"), name="admin")
    """

    def __init__(self, description: str | None = None) -> None:
        if description is not None:
            self.route.description = description


class _RoutingProxy:
    """Proxy for configuring the router of a RoutingClass instance.

    Provides plugin configuration for the owner's router. Access via the
    ``routing`` property on any RoutingClass instance. For navigation and
    introspection use the router's ``node(path)`` / ``nodes(basepath=...)``.

    Main operations:
        - ``configure(target, **options)``: Configure plugin settings
        - ``attach_instance(child, name=...)``: Delegates to owner's attach_instance

    Target syntax for configure():
        - ``"plugin"`` - Global plugin config
        - ``"plugin/handler"`` - Per-handler config
        - ``"plugin/pattern*"`` - Glob pattern matching
        - ``"?"`` - Describe the router and its configuration

    Example:
        >>> svc.routing.configure("logging", before=False)
        >>> svc.routing.configure("auth/admin_*", rule="admin")
        >>> svc.routing.configure("?")  # introspection
    """

    _owner: RoutingClass

    def __init__(self, owner: RoutingClass):
        object.__setattr__(self, "_owner", owner)

    # Helpers -------------------------------------------------
    def _parse_target(self, target: str) -> tuple[str, str]:
        """Parse 'plugin/selector' into (plugin, selector)."""
        if "/" in target:
            plugin_part, selector = target.split("/", 1)
        else:
            plugin_part, selector = target, "_all_"
        plugin_part = plugin_part.strip()
        selector = selector.strip() or "_all_"
        if not plugin_part:
            raise ValueError("Plugin name cannot be empty")
        return plugin_part, selector

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

    def _describe_router(self, router) -> dict[str, Any]:
        """Build introspection dict for a router (recursing into children)."""
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

    def attach_instance(self, child: RoutingClass, *, name: str | None = None) -> None:
        """Attach a child instance. Delegates to owner's attach_instance.

        Args:
            child: The RoutingClass instance to attach.
            name: Alias under which the child's router is linked.

        Example:
            >>> svc.routing.attach_instance(child, name="sales")
        """
        self._owner.attach_instance(child, name=name)

    def configure(self, target: Any, **options: Any):
        """Configure router plugins.

        Args:
            target: Configuration target. Can be:
                - ``"?"`` to describe the router
                - ``"plugin"`` for global plugin config
                - ``"plugin/selector"`` for handler-specific config
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
            return self._describe_router(self._owner.route)
        plugin_name, selector = self._parse_target(target)
        bound_router = self._owner.route
        plugin = getattr(bound_router, plugin_name, None)
        if plugin is None:
            raise AttributeError(f"No plugin named '{plugin_name}' on router")
        if not options:
            raise ValueError("No configuration options provided")
        selector = selector or "_all_"
        if selector.lower() == "_all_":
            plugin.configure(_target="_all_", **options)
            return {"target": target, "updated": ["_all_"]}
        matches = self._match_handlers(bound_router, selector)
        if not matches:
            raise KeyError(f"No handlers matching '{selector}'")
        for handler in matches:
            plugin.configure(_target=handler, **options)
        return {"target": target, "updated": sorted(matches)}


def is_routing_class(obj: Any) -> bool:
    """Return True when ``obj`` is a RoutingClass instance."""
    return safe_is_instance(obj, "genro_routes.core.routing.RoutingClass")  # type: ignore[no-any-return]


def is_result_wrapper(obj: Any) -> bool:
    """Return True when ``obj`` is a ResultWrapper instance."""
    return isinstance(obj, ResultWrapper)
