"""Plugin-free router runtime for Genro Routes.

This module exposes :class:`BaseRouter`, which binds methods on an object
instance, resolves path selectors (using '/' separator), and exposes rich
introspection without any plugin logic. Subclasses add middleware but must
preserve these semantics.

Constructor and slots
---------------------
Constructor signature::

    BaseRouter(owner, name=None, prefix=None, *, description=None,
               get_default_handler=None, get_use_smartasync=None,
               get_kwargs=None, branch=False, parent_router=None)

- ``owner`` is required; ``None`` raises ``ValueError``. Routers are bound to
  this instance and never re-bound.
- ``description``: optional human-readable description of this router's purpose.
  Included in ``nodes()`` output for documentation/introspection.
- ``parent_router``: optional parent router. When provided, this router is
  automatically attached as a child using ``name`` as the alias. Requires
  ``name`` to be set; raises ``ValueError`` on name collision.
- Slots: ``instance``, ``name``, ``prefix``, ``description`` (optional router description),
  ``_entries`` (logical name → MethodEntry with handler), ``_children`` (name → child router),
  ``_get_defaults`` (SmartOptions defaults).

Lazy binding
------------
Routers use lazy binding: methods decorated with ``@route`` are discovered and
registered automatically on first use (get/call/nodes). No explicit bind() call
is needed.

Marker discovery
----------------
``_iter_marked_methods`` walks the reversed MRO of ``type(owner)`` (child first
wins), scans ``__dict__`` for plain functions carrying ``_route_decorator_kw``
markers. Only markers whose ``name`` matches this router's ``name`` are used.

Handler table and wrapping
--------------------------
- ``_register_callable`` creates a ``MethodEntry`` and stores it in ``_entries``.
- ``_rebuild_handlers`` updates each entry's ``handler`` attribute by passing through
  ``_wrap_handler`` (default: passthrough). Subclasses may inject middleware.

Lookup and execution
--------------------
- ``get(selector, **options)`` resolves ``selector`` via ``_resolve_path``.
  A path string (using '/' separator) traverses children. Missing handlers
  fall back to ``default_handler`` (if provided) else raise ``NotImplementedError``.

- ``__getitem__`` aliases ``get``; ``call`` fetches then invokes the handler.

Children (instance hierarchies)
-------------------------------
``attach_instance(child, name=None)`` / ``detach_instance(child)``

- ``attach_instance`` connects routers exposed on a ``RoutedClass`` child that
  is already stored as an attribute on the parent instance.
- Attached child routers inherit plugins via ``_on_attached_to_parent``.

Introspection
-------------
- ``nodes(**kwargs)`` builds a nested dict of routers and entries respecting
  filters. Returns dict with ``entries`` and ``routers`` keys only if non-empty.
  Output includes ``description`` (router's description) and ``owner_doc``
  (owner class docstring) for documentation purposes.

Output modes
------------
- ``nodes(mode="openapi")`` returns flat OpenAPI format with all paths merged.
- ``nodes(mode="h_openapi")`` returns hierarchical OpenAPI format preserving
  the router tree structure with ``description`` and ``owner_doc`` at each level.

Hooks for subclasses
--------------------
- ``_wrap_handler``: override to wrap callables (middleware stack).
- ``_after_entry_registered``: invoked after registering a handler.
- ``_on_attached_to_parent``: invoked when attached via ``attach_instance``.
- ``_describe_entry_extra``: allow subclasses to extend per-entry description.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from typing import Any, get_type_hints

from genro_toolbox import SmartOptions
from genro_toolbox.typeutils import safe_is_instance

from genro_routes.plugins._base_plugin import MethodEntry

from .router_interface import RouterInterface

__all__ = ["BaseRouter"]


class BaseRouter(RouterInterface):
    """Plugin-free router bound to an object instance.

    Responsibilities:
        - Register bound methods/functions with logical names (optionally via markers)
        - Resolve path selectors (using '/' separator) across child routers
        - Expose handler tables and introspection data
        - Provide hooks for subclasses to wrap handlers or filter introspection
    """

    __slots__ = (
        "instance",
        "name",
        "prefix",
        "description",
        "__entries_raw",
        "_children",
        "_get_defaults",
        "_is_branch",
        "_bound",
    )

    def __init__(
        self,
        owner: Any,
        name: str | None = None,
        prefix: str | None = None,
        *,
        description: str | None = None,
        get_default_handler: Callable | None = None,
        get_use_smartasync: bool | None = None,
        get_kwargs: dict[str, Any] | None = None,
        branch: bool = False,
        parent_router: BaseRouter | None = None,
    ) -> None:
        if owner is None:
            raise ValueError("Router requires a parent instance")
        if not safe_is_instance(owner, "genro_routes.core.routed.RoutedClass"):
            raise TypeError(
                f"Router owner must be a RoutedClass instance, got {type(owner).__name__}. "
                "Inherit from RoutedClass to use Router."
            )
        self.instance = owner
        self.name = name
        self.prefix = prefix or ""
        self.description = description
        self._is_branch = bool(branch)
        self._bound = False
        self.__entries_raw: dict[str, MethodEntry] = {}
        self._children: dict[str, BaseRouter] = {}
        defaults: dict[str, Any] = dict(get_kwargs or {})
        if get_default_handler is not None:
            defaults.setdefault("default_handler", get_default_handler)
        if get_use_smartasync is not None:
            defaults.setdefault("use_smartasync", get_use_smartasync)
        self._get_defaults: dict[str, Any] = defaults
        self._register_with_owner()

        # Attach to parent router if specified
        if parent_router is not None:
            alias = name
            if not alias:
                raise ValueError("Child router must have a name when using parent_router")
            if alias in parent_router._children and parent_router._children[alias] is not self:
                raise ValueError(f"Child name collision: {alias!r}")
            parent_router._children[alias] = self
            self._on_attached_to_parent(parent_router)

    # ------------------------------------------------------------------
    # Lazy binding property
    # ------------------------------------------------------------------
    @property
    def _entries(self) -> dict[str, MethodEntry]:
        """Access entries dict, triggering lazy binding if needed."""
        if not self._bound:
            self._bind()
        return self.__entries_raw

    @_entries.setter
    def _entries(self, value: dict[str, MethodEntry]) -> None:
        self.__entries_raw = value

    def _is_known_plugin(self, prefix: str) -> bool:
        try:
            from genro_routes.core.router import Router  # type: ignore
        except Exception:  # pragma: no cover - import safety
            return False
        return prefix in Router.available_plugins()

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------
    def _register_with_owner(self) -> None:
        hook = getattr(self.instance, "_register_router", None)
        if callable(hook):
            hook(self)

    def _add_entry(
        self,
        target: Any,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        replace: bool = False,
        **options: Any,
    ) -> BaseRouter:
        """Register handler(s) on this router.

        Args:
            target: Callable, attribute name(s), comma-separated string, or wildcard marker.
            name: Logical name override for this entry.
            metadata: Extra metadata stored on the MethodEntry.
            replace: Allow overwriting an existing logical name.
            options: Extra metadata merged into entry metadata.

        Returns:
            self (to allow chaining).

        Raises:
            ValueError: on handler name collision when replace is False.
            AttributeError: when resolving missing attributes on owner.
            TypeError: on unsupported target type.
        """
        if self._is_branch:
            raise ValueError("Branch routers cannot register handlers")
        entry_name = name
        # Split plugin-scoped options (<plugin>_<key>) from core options
        plugin_options: dict[str, dict[str, Any]] = {}
        core_options: dict[str, Any] = {}
        for key, value in options.items():
            if "_" in key:
                plugin_name, plug_key = key.split("_", 1)
                if plugin_name and plug_key and self._is_known_plugin(plugin_name):
                    plugin_options.setdefault(plugin_name, {})[plug_key] = value
                    continue
            core_options[key] = value

        if isinstance(target, (list, tuple, set)):
            for entry in target:
                self._add_entry(
                    entry,
                    name=entry_name,
                    metadata=dict(metadata or {}),
                    replace=replace,
                    **core_options,
                )
            return self

        if isinstance(target, str):
            target = target.strip()
            if not target:
                return self
            if target in {"*", "_all_", "__all__"}:
                self._register_marked(
                    name=entry_name,
                    metadata=metadata,
                    replace=replace,
                    extra=core_options,
                    plugin_options=plugin_options,
                )
                self._bound = True  # Mark as bound after marker discovery
                return self
            if "," in target:
                for chunk in target.split(","):
                    chunk = chunk.strip()
                    if chunk:
                        self._add_entry(
                            chunk,
                            name=entry_name,
                            metadata=dict(metadata or {}),
                            replace=replace,
                            **core_options,
                        )
                return self
            bound = getattr(self.instance, target)
        elif callable(target):
            bound = (
                target
                if inspect.ismethod(target)
                else target.__get__(self.instance, type(self.instance))
            )
        else:
            raise TypeError(f"Unsupported entry target: {target!r}")

        entry_meta = dict(metadata or {})
        entry_meta.update(core_options)
        self._register_callable(
            bound,
            name=entry_name,
            metadata=entry_meta,
            replace=replace,
            plugin_options=plugin_options,
        )
        return self

    def _register_callable(
        self,
        bound: Callable,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        replace: bool = False,
        plugin_options: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        logical_name = self._resolve_name(bound.__name__, name_override=name)
        if logical_name in self._entries and not replace:
            raise ValueError(f"Handler name collision: {logical_name}")
        entry = MethodEntry(
            name=logical_name,
            func=bound,
            router=self,
            plugins=[],
            metadata=dict(metadata or {}),
        )
        # Attach plugin-scoped config to metadata for later consumption by plugin-enabled routers.
        if plugin_options:
            entry.metadata["plugin_config"] = plugin_options
        self._entries[logical_name] = entry
        self._after_entry_registered(entry)
        self._rebuild_handlers()

    def _register_marked(
        self,
        *,
        name: str | None,
        metadata: dict[str, Any] | None,
        replace: bool,
        extra: dict[str, Any],
        plugin_options: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        for func, marker in self._iter_marked_methods():
            entry_override = marker.pop("entry_name", None)
            entry_name = name if name is not None else entry_override
            entry_meta = dict(metadata or {})
            entry_meta.update(marker)
            entry_meta.update(extra)
            # Split plugin-scoped options from marker payload as well
            marker_plugin_opts: dict[str, dict[str, Any]] = {}
            core_marker: dict[str, Any] = {}
            for key, value in entry_meta.items():
                if "_" in key:
                    plugin_name, plug_key = key.split("_", 1)
                    if plugin_name and plug_key and self._is_known_plugin(plugin_name):
                        marker_plugin_opts.setdefault(plugin_name, {})[plug_key] = value
                        continue
                core_marker[key] = value
            entry_meta = core_marker
            merged_plugin_opts: dict[str, dict[str, Any]] = {}
            if plugin_options:
                merged_plugin_opts.update(plugin_options)
            for pname, pdata in marker_plugin_opts.items():
                merged_plugin_opts.setdefault(pname, {}).update(pdata)
            bound = func.__get__(self.instance, type(self.instance))
            self._register_callable(
                bound,
                name=entry_name,
                metadata=entry_meta,
                replace=replace,
                plugin_options=merged_plugin_opts or None,
            )

    def _iter_marked_methods(self) -> Iterator[tuple[Callable, dict[str, Any]]]:
        cls = type(self.instance)
        main_router = getattr(cls, "main_router", None)
        seen: set[int] = set()
        for base in reversed(cls.__mro__):
            base_dict = vars(base)
            for _attr_name, value in base_dict.items():
                if not inspect.isfunction(value):
                    continue
                func_id = id(value)
                if func_id in seen:
                    continue
                seen.add(func_id)
                markers = getattr(value, "_route_decorator_kw", None)
                if not markers:
                    continue
                for marker in markers:
                    marker_name = marker.get("name")
                    # If marker_name is None, use class's main_router
                    if marker_name is None:
                        marker_name = main_router
                    if marker_name != self.name:
                        continue
                    payload = dict(marker)
                    payload.pop("name", None)
                    yield value, payload

    def _resolve_name(self, func_name: str, *, name_override: str | None) -> str:
        if name_override:
            return name_override
        if self.prefix and func_name.startswith(self.prefix):
            return func_name[len(self.prefix) :]
        return func_name

    def _wrap_handler(
        self, entry: MethodEntry, call_next: Callable
    ) -> Callable:  # pragma: no cover - overridden by plugin routers
        return call_next

    # ------------------------------------------------------------------
    # Binding (finalization)
    # ------------------------------------------------------------------
    def _bind(self) -> None:
        """Finalize router configuration and trigger route discovery.

        Internal method called automatically on first use (lazy binding).
        Discovers @route decorated methods and registers them.
        """
        if self._bound:
            return  # Already bound, no-op
        self._bound = True  # Set BEFORE work to avoid recursion via properties
        if not self._is_branch:
            self._add_entry("*")

    def _require_bound(self, operation: str) -> None:
        """Ensure the router is bound, auto-binding if needed.

        Args:
            operation: Name of the operation being attempted (unused, kept for API).

        This implements lazy binding: the router auto-binds on first use.
        """
        if not self._bound:
            self._bind()

    # ------------------------------------------------------------------
    # Handler rebuilding
    # ------------------------------------------------------------------
    def _rebuild_handlers(self) -> None:
        """Rebuild wrapped handlers for all entries."""
        for entry in self.__entries_raw.values():
            entry.handler = self._wrap_handler(entry, entry.func)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, selector: str, **options: Any) -> Callable | RouterInterface | None:
        """Resolve and return a handler, child router, or None for the given selector.

        Path selectors traverse attached children using '/'. Returns:
        - A callable if the selector points to a handler
        - A RouterInterface if the selector points to a child router
        - None if nothing is found and no default_handler is provided

        Falls back to ``default_handler`` if provided and nothing is found.
        When ``use_smartasync`` is true, handler callables are wrapped accordingly.

        When ``partial=True`` and the path cannot be fully resolved, returns a
        ``functools.partial`` wrapping the last valid target's ``call()`` method
        with the unconsumed path segments as positional arguments. This enables
        catch-all routing patterns::

            # Given: alfa/beta exists, gamma/delta does not
            result = router.get("alfa/beta/gamma/delta", partial=True)
            # Returns: partial(beta_router.call, "gamma/delta")
            # Call with kwargs:
            result(x=12, y=14)  # executes beta.call("gamma/delta", x=12, y=14)

        Raises:
            RuntimeError: If the router has not been bound yet.
        """
        opts = SmartOptions(options, defaults=self._get_defaults)
        default = getattr(opts, "default_handler", None)
        use_smartasync = getattr(opts, "use_smartasync", False)
        use_partial = getattr(opts, "partial", False)

        # Handle path with "/" by delegating to child routers
        if "/" in selector:
            first, rest = selector.split("/", 1)
            child = self._children.get(first)
            if child is None:
                # Child not found - check if partial resolution is requested
                if use_partial:
                    # Check if first segment is an entry (catch-all pattern)
                    entry = self._entries.get(first)
                    if entry is not None:
                        handler = entry.handler
                        if use_smartasync:
                            from smartasync import smartasync  # type: ignore

                            handler = smartasync(handler)
                        # Return partial with unconsumed path as args
                        return functools.partial(handler, *rest.split("/"))
                    # No entry either, return partial on this router's call
                    return functools.partial(self.call, selector)
                if default is not None:
                    return default  # type: ignore[no-any-return]
                return None
            # Delegate to child router's get()
            result = child.get(rest, **options)
            if result is None and use_partial:
                # Child couldn't resolve rest - return partial on child's call
                return functools.partial(child.call, rest)
            return result

        # Single segment: check entries first, then children
        entry = self._entries.get(selector)
        if entry is not None:
            handler = entry.handler
            if use_smartasync:
                from smartasync import smartasync  # type: ignore

                handler = smartasync(handler)
            return handler

        child_router = self._children.get(selector)
        if child_router is not None:
            return child_router

        # Nothing found - use default or return None
        if use_partial:
            # Return partial on this router's call with the selector
            return functools.partial(self.call, selector)
        if default is not None:
            return default  # type: ignore[no-any-return]

        return None

    __getitem__ = get

    def call(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        """Fetch and invoke a handler in one step.

        Raises:
            RuntimeError: If the router has not been bound yet.
        """
        handler = self.get(selector)
        if handler is None or isinstance(handler, BaseRouter):
            raise NotImplementedError(f"No callable handler found for '{selector}'")
        return handler(*args, **kwargs)  # type: ignore[operator]

    # ------------------------------------------------------------------
    # Children management (via attach_instance/detach_instance)
    # ------------------------------------------------------------------
    def attach_instance(self, routed_child: Any, *, name: str | None = None) -> BaseRouter:
        """Attach a RoutedClass instance with optional alias mapping."""
        if not safe_is_instance(routed_child, "genro_routes.core.routed.RoutedClass"):
            raise TypeError("attach_instance() requires a RoutedClass instance")
        existing_parent = getattr(routed_child, "_routed_parent", None)
        if existing_parent is not None and existing_parent is not self.instance:
            raise ValueError("attach_instance() rejected: child already bound to another parent")

        candidates = self._collect_child_routers(routed_child)
        if not candidates:
            raise TypeError(
                f"Object {routed_child!r} does not expose Router instances"
            )  # pragma: no cover

        mapping: dict[str, str] = {}
        tokens = [chunk.strip() for chunk in (name.split(",") if name else []) if chunk.strip()]
        parent_has_multiple = len(self.instance._routers) > 1

        if len(candidates) == 1:
            # Single child router: alias optional unless parent has multiple routers.
            if parent_has_multiple and not tokens:
                raise ValueError(
                    "attach_instance() requires alias when parent has multiple routers"
                )  # pragma: no cover
            alias: str = tokens[0] if tokens else name or candidates[0][0] or candidates[0][1].name  # type: ignore[assignment]
            orig_attr, _ = candidates[0]
            mapping[orig_attr] = alias
        else:
            # Multiple child routers.
            if parent_has_multiple and not tokens:
                raise ValueError(
                    "attach_instance() requires mapping when parent has multiple routers"
                )  # pragma: no cover
            if not tokens:
                # Auto-mapping: alias = child router name/attr
                for orig_attr, router in candidates:
                    alias = router.name or orig_attr
                    mapping[orig_attr] = alias
            else:
                candidate_names = {attr for attr, _ in candidates}
                for token in tokens:
                    if ":" not in token:
                        raise ValueError(
                            "attach_instance() with multiple routers requires mapping 'child:alias'"
                        )  # pragma: no cover
                    orig, alias = [part.strip() for part in token.split(":", 1)]
                    if not orig or not alias:
                        raise ValueError(
                            "attach_instance() mapping requires both child and alias"
                        )  # pragma: no cover
                    if orig not in candidate_names:
                        raise ValueError(
                            f"Unknown child router {orig!r} in mapping"
                        )  # pragma: no cover
                    if orig in mapping:
                        raise ValueError(f"Duplicate mapping for {orig!r}")  # pragma: no cover
                    mapping[orig] = alias
                # Unmapped child routers are simply not attached.

        attached: BaseRouter | None = None
        for attr_name, router in candidates:
            alias = mapping.get(attr_name)  # type: ignore[assignment]
            if alias is None:
                continue  # pragma: no cover - unmapped child router is skipped
            if alias in self._children and self._children[alias] is not router:
                raise ValueError(f"Child name collision: {alias}")
            self._children[alias] = router
            router._on_attached_to_parent(self)
            attached = router

        if getattr(routed_child, "_routed_parent", None) is not self.instance:
            object.__setattr__(routed_child, "_routed_parent", self.instance)
        assert attached is not None
        return attached

    def detach_instance(self, routed_child: Any) -> BaseRouter:
        """Detach all routers belonging to a RoutedClass instance."""
        if not safe_is_instance(routed_child, "genro_routes.core.routed.RoutedClass"):
            raise TypeError("detach_instance() requires a RoutedClass instance")
        removed: list[str] = []
        for alias, router in list(self._children.items()):
            if router.instance is routed_child:
                removed.append(alias)
                self._children.pop(alias, None)

        if getattr(routed_child, "_routed_parent", None) is self.instance:
            object.__setattr__(routed_child, "_routed_parent", None)

        # No hard error if nothing was removed; detach is best-effort.
        return routed_child  # type: ignore[no-any-return]

    def _collect_child_routers(self, source: Any) -> list[tuple[str, BaseRouter]]:
        """Return all routers registered in ``source``'s registry."""
        return list(source._routers.items())

    # ------------------------------------------------------------------
    # Routing helpers
    # ------------------------------------------------------------------
    def _resolve_path(self, selector: str) -> tuple[RouterInterface, str]:
        if "/" not in selector:
            return self, selector
        node: RouterInterface = self
        parts = selector.split("/")
        for segment in parts[:-1]:
            # Use get() to allow non-BaseRouter children (e.g., StaticRouter)
            child = node._children.get(segment) if hasattr(node, "_children") else None
            if child is None:
                raise KeyError(segment)
            node = child
        return node, parts[-1]

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    def nodes(
        self,
        basepath: str | None = None,
        lazy: bool = False,
        mode: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a tree of routers/entries/metadata respecting filters.

        Args:
            basepath: Optional path to start from (e.g., "child/grandchild").
                      If provided, returns nodes starting from that point
                      in the hierarchy instead of from this router.
            lazy: If True, child routers are returned as router references
                  instead of recursively expanded. Use basepath to navigate
                  and expand specific children on demand.
            mode: Output format mode. Supported modes:

                  - None: Standard introspection format with full metadata.
                  - "openapi": Flat OpenAPI format with all paths merged.
                  - "h_openapi": Hierarchical OpenAPI format preserving
                    the router tree structure.

            **kwargs: Filter arguments passed to plugins via allow_entry().

        Returns:
            A dict containing:

            - ``name``: Router name
            - ``description``: Router description (if set)
            - ``owner_doc``: Owner class docstring (for documentation)
            - ``router``: Reference to this router
            - ``instance``: Owner instance
            - ``plugin_info``: Plugin configuration info
            - ``entries``: Dict of entry names to entry info (if any)
            - ``routers``: Dict of child names to child nodes (if any)

            When mode is specified, output is translated to that format.
        """
        if basepath:
            target = self.get(basepath)
            if not isinstance(target, BaseRouter):
                return {}
            return target.nodes(lazy=lazy, mode=mode, **kwargs)
        filter_args = self._prepare_filter_args(**kwargs)

        entries = {
            entry.name: self._entry_node_info(entry)
            for entry in self._entries.values()
            if self._allow_entry(entry, **filter_args)
        }

        routers: dict[str, Any]
        if lazy:
            # In lazy mode, just return the router references - use basepath to expand
            routers = dict(self._children)
        else:
            routers = {
                child_name: child.nodes(**kwargs) for child_name, child in self._children.items()
            }
            # Remove empty routers only in non-lazy mode
            routers = {k: v for k, v in routers.items() if v}

        # If nothing, return empty dict
        if not entries and not routers:
            return {}

        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "owner_doc": self.instance.__class__.__doc__,
            "router": self,
            "instance": self.instance,
            "plugin_info": self._get_plugin_info(),
        }
        if entries:
            result["entries"] = entries
        if routers:
            result["routers"] = routers

        # Translate to requested format if mode specified
        if mode:
            translator = getattr(self, f"_translate_{mode}", None)
            if translator is None:
                raise ValueError(f"Unknown mode: {mode}")
            translated: dict[str, Any] = translator(result, lazy=lazy)
            return translated

        return result

    def node(self, path: str, mode: str | None = None) -> dict[str, Any]:
        """Return info about a single node (router or entry) at the given path.

        Unlike nodes() which returns the full subtree, this method returns
        information about just one specific node without recursion.

        Args:
            path: Path to the node (e.g., "entry_name" or "child/grandchild/entry").
            mode: Output format mode. Supported modes:

                  - None: Standard introspection format.
                  - "openapi": OpenAPI format for entries.

        Returns:
            A dict containing node info:

            For a router:
                - ``type``: "router"
                - ``name``: Router name
                - ``path``: Full path to this router
                - ``description``: Router description (if set)
                - ``owner_doc``: Owner class docstring

            For an entry:
                - ``type``: "entry"
                - ``name``: Entry name
                - ``path``: Full path to this entry
                - ``doc``: Entry docstring
                - ``metadata``: Entry metadata

            Returns empty dict if path not found.

            When mode="openapi", entry output includes OpenAPI format.
        """
        target = self.get(path)
        if target is None:
            return {}

        # Calculate full path
        full_path = path

        if isinstance(target, BaseRouter):
            return {
                "type": "router",
                "name": target.name,
                "path": full_path,
                "description": target.description,
                "owner_doc": target.instance.__class__.__doc__,
            }

        # It's an entry (callable) - find the MethodEntry
        # Resolve to get the entry directly
        if "/" in path:
            parent_path, entry_name = path.rsplit("/", 1)
            parent = self.get(parent_path)
            if not isinstance(parent, BaseRouter):
                return {}
            entry = parent._entries.get(entry_name)
        else:
            entry = self._entries.get(path)

        if entry is None:
            return {}

        result: dict[str, Any] = {
            "type": "entry",
            "name": entry.name,
            "path": full_path,
            "doc": inspect.getdoc(entry.func) or entry.func.__doc__ or "",
            "metadata": entry.metadata,
        }

        if mode == "openapi":
            entry_info = self._entry_node_info(entry)
            result["openapi"] = self._entry_info_to_openapi(entry.name, entry_info)

        return result

    def _translate_openapi(
        self,
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
            and "routers" for children in lazy mode.
        """
        paths: dict[str, Any] = {}

        # Convert entries to OpenAPI paths
        entries = nodes_data.get("entries", {})
        for entry_name, entry_info in entries.items():
            path = f"{path_prefix}/{entry_name}" if path_prefix else f"/{entry_name}"
            paths[path] = self._entry_info_to_openapi(entry_name, entry_info)

        # Handle child routers
        routers_data = nodes_data.get("routers", {})
        routers: dict[str, Any]
        if lazy:
            # In lazy mode, just pass through router references
            routers = dict(routers_data)
        else:
            # In eager mode, recursively translate and merge paths
            for child_name, child_data in routers_data.items():
                child_prefix = f"{path_prefix}/{child_name}" if path_prefix else f"/{child_name}"
                child_openapi = self._translate_openapi(
                    child_data, lazy=False, path_prefix=child_prefix
                )
                paths.update(child_openapi.get("paths", {}))
            routers = {}

        result: dict[str, Any] = {"paths": paths}
        if routers:
            result["routers"] = routers
        return result

    def _translate_h_openapi(
        self,
        nodes_data: dict[str, Any],
        lazy: bool = False,
    ) -> dict[str, Any]:
        """Translate nodes() output to hierarchical OpenAPI format.

        Unlike _translate_openapi which flattens all paths, this preserves
        the router hierarchy while converting entries to OpenAPI format.

        Args:
            nodes_data: Output from nodes() in standard format.
            lazy: If True, child routers are returned as router references.

        Returns:
            Dict with "paths" containing local OpenAPI path items,
            and "routers" containing nested h_openapi structures for children.
        """
        paths: dict[str, Any] = {}

        # Convert local entries to OpenAPI paths (without prefix)
        entries = nodes_data.get("entries", {})
        for entry_name, entry_info in entries.items():
            path = f"/{entry_name}"
            paths[path] = self._entry_info_to_openapi(entry_name, entry_info)

        # Handle child routers
        routers_data = nodes_data.get("routers", {})
        routers: dict[str, Any]
        if lazy:
            # In lazy mode, just pass through router references
            routers = dict(routers_data)
        else:
            # In eager mode, recursively translate each child (maintaining hierarchy)
            routers = {}
            for child_name, child_data in routers_data.items():
                child_h_openapi = self._translate_h_openapi(child_data, lazy=False)
                if child_h_openapi:
                    routers[child_name] = child_h_openapi

        result: dict[str, Any] = {
            "description": nodes_data.get("description"),
            "owner_doc": nodes_data.get("owner_doc"),
        }
        if paths:
            result["paths"] = paths
        if routers:
            result["routers"] = routers
        return result

    def _entry_info_to_openapi(self, name: str, entry_info: dict[str, Any]) -> dict[str, Any]:
        """Convert entry info dict to OpenAPI path item format.

        HTTP method determination priority:
        1. Explicit override via openapi plugin config (openapi_method in metadata)
        2. Guessed from function signature (_guess_http_method)
        """
        func = entry_info.get("callable")
        doc = entry_info.get("doc", "")
        summary = doc.split("\n")[0] if doc else name
        metadata = entry_info.get("metadata", {})

        # Determine HTTP method: check for explicit override first
        openapi_config = metadata.get("plugin_config", {}).get("openapi", {})
        explicit_method = openapi_config.get("method")
        if explicit_method:
            http_method = explicit_method.lower()
        elif func:
            http_method = self._guess_http_method(func)
        else:
            http_method = "post"

        operation: dict[str, Any] = {
            "operationId": name,
            "summary": summary,
        }
        if doc:
            operation["description"] = doc

        # Add tags if specified in openapi config
        tags = openapi_config.get("tags")
        if tags:
            operation["tags"] = tags if isinstance(tags, list) else [tags]

        # Extract parameters from pydantic metadata if available, otherwise create model on-the-fly
        pydantic_meta = metadata.get("pydantic", {})
        model = pydantic_meta.get("model")

        if not model and func:
            # Create pydantic model on-the-fly (pydantic is a required dependency)
            model = self._create_pydantic_model_for_func(func)

        if model and hasattr(model, "model_json_schema"):
            schema = model.model_json_schema()
            # GET uses query parameters, POST/PUT/PATCH use requestBody
            if http_method == "get":
                # Convert schema properties to OpenAPI parameters
                parameters = self._schema_to_parameters(schema)
                if parameters:
                    operation["parameters"] = parameters
            else:
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": schema}},
                }

        # Add return type if available
        if func:
            try:
                hints = get_type_hints(func)
                return_hint = hints.get("return")
                if return_hint:
                    operation["responses"] = {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": self._python_type_to_openapi_schema(return_hint)
                                }
                            },
                        }
                    }
            except Exception:
                pass

        if "responses" not in operation:
            operation["responses"] = {"200": {"description": "Successful response"}}

        return {http_method: operation}

    @staticmethod
    def _create_pydantic_model_for_func(func: Callable) -> Any | None:
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
            # Pydantic can't handle some types (e.g., arbitrary classes without config)
            return None

    @staticmethod
    def _schema_to_parameters(schema: dict[str, Any]) -> list[dict[str, Any]]:
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
    def _python_type_to_openapi_schema(python_type: Any) -> dict[str, Any]:
        """Convert Python type to OpenAPI schema dict using pydantic.

        Uses pydantic's TypeAdapter to generate JSON schema for any type.
        """
        from pydantic import TypeAdapter

        try:
            adapter = TypeAdapter(python_type)
            return adapter.json_schema()
        except Exception:
            # Fallback for types pydantic can't handle
            return {"type": "object"}

    @staticmethod
    def _guess_http_method(func: Callable) -> str:
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

        # Has parameters → POST
        if hints:
            return "post"

        # No parameters, no return → POST (side effect)
        if return_hint is None or return_hint is type(None):
            return "post"

        # No parameters, has return → GET (read operation)
        return "get"

    def _entry_node_info(self, entry: MethodEntry) -> dict[str, Any]:
        """Build info dict for a single entry."""
        info: dict[str, Any] = {
            "name": entry.name,
            "callable": entry.func,
            "metadata": entry.metadata,
            "doc": inspect.getdoc(entry.func) or entry.func.__doc__ or "",
        }
        extra = self._describe_entry_extra(entry, info)
        if extra:
            info.update(extra)
        return info

    def _get_plugin_info(self) -> dict[str, Any]:
        """Build plugin_info dict from _plugin_info store."""
        info_source = getattr(self, "_plugin_info", {}) or {}
        return {
            pname: {
                key: {
                    "config": dict(slot.get("config", {})),
                    "locals": dict(slot.get("locals", {})),
                }
                for key, slot in pdata.items()
            }
            for pname, pdata in info_source.items()
        }

    # ------------------------------------------------------------------
    # Plugin hooks (no-op for BaseRouter)
    # ------------------------------------------------------------------
    def iter_plugins(self) -> list[Any]:  # pragma: no cover - base router has no plugins
        return []

    # ------------------------------------------------------------------
    # Dict-like interface (entries + children as unified namespace)
    # ------------------------------------------------------------------
    def __iter__(self) -> Iterator[str]:
        """Iterate over all node names (entries + children)."""
        yield from self._entries.keys()
        yield from self._children.keys()

    def __len__(self) -> int:
        """Return total count of nodes (entries + children)."""
        return len(self._entries) + len(self._children)

    def __contains__(self, name: object) -> bool:
        """Check if name exists in entries or children."""
        return name in self._entries or name in self._children

    def keys(self) -> Iterator[str]:
        """Return all node names (entries + children)."""
        yield from self._entries.keys()
        yield from self._children.keys()

    def values(self) -> Iterator[MethodEntry | BaseRouter]:
        """Return all nodes (entries + children)."""
        yield from self._entries.values()
        yield from self._children.values()

    def items(self) -> Iterator[tuple[str, MethodEntry | BaseRouter]]:
        """Return all (name, node) pairs (entries + children)."""
        yield from self._entries.items()
        yield from self._children.items()

    def _on_attached_to_parent(
        self, parent: BaseRouter
    ) -> None:  # pragma: no cover - hook for subclasses
        """Hook for plugin-enabled routers to override when attached."""
        return None

    def _after_entry_registered(
        self, entry: MethodEntry
    ) -> None:  # pragma: no cover - hook for subclasses
        """Hook invoked after a handler is registered (subclasses may override)."""
        return None

    def _describe_entry_extra(
        self, entry: MethodEntry, base_description: dict[str, Any]
    ) -> dict[str, Any]:  # pragma: no cover - overridden when plugins present
        """Hook used by subclasses to inject extra description data."""
        return {}

    def _prepare_filter_args(self, **raw_filters: Any) -> dict[str, Any]:
        """Return normalized filters understood by subclasses (default: passthrough)."""
        return {key: value for key, value in raw_filters.items() if value not in (None, False)}

    def _allow_entry(self, entry: MethodEntry, **filters: Any) -> bool:
        """Hook used by subclasses to decide if an entry is exposed."""
        return True
