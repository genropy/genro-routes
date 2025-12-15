"""Plugin-free router runtime for Genro Routes.

This module exposes :class:`BaseRouter`, which binds methods on an object
instance, resolves path selectors (using '/' separator), and exposes rich
introspection without any plugin logic. Subclasses add middleware but must
preserve these semantics.

Constructor and slots
---------------------
Constructor signature::

    BaseRouter(owner, name=None, prefix=None, *,
               get_default_handler=None, get_use_smartasync=None,
               get_kwargs=None, branch=False, auto_discover=True,
               auto_selector="*", parent_router=None)

- ``owner`` is required; ``None`` raises ``ValueError``. Routers are bound to
  this instance and never re-bound.
- ``parent_router``: optional parent router. When provided, this router is
  automatically attached as a child using ``name`` as the alias. Requires
  ``name`` to be set; raises ``ValueError`` on name collision.
- Slots: ``instance``, ``name``, ``prefix`` (string trimmed from function names),
  ``_entries`` (logical name → MethodEntry), ``_handlers`` (name → callable),
  ``_children`` (name → child router), ``_get_defaults`` (SmartOptions defaults).

Registration and naming
-----------------------
``add_entry(target, *, name=None, metadata=None, replace=False, **options)``

- Accepts a callable or string/iterable of attribute names. Comma-separated
  strings are split and each processed. Empty/whitespace-only strings are
  ignored. ``replace=False`` raises on logical name collision.

- Special markers ``"*"``, ``"_all_"``, ``"__all__"`` trigger marker discovery
  via ``_register_marked``.

Marker discovery
----------------
``_iter_marked_methods`` walks the reversed MRO of ``type(owner)`` (child first
wins), scans ``__dict__`` for plain functions carrying ``_route_decorator_kw``
markers. Only markers whose ``name`` matches this router's ``name`` are used.

Handler table and wrapping
--------------------------
- ``_register_callable`` creates a ``MethodEntry`` and stores it in ``_entries``.
- ``_rebuild_handlers`` recreates ``_handlers`` by passing each entry through
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

Hooks for subclasses
--------------------
- ``_wrap_handler``: override to wrap callables (middleware stack).
- ``_after_entry_registered``: invoked after registering a handler.
- ``_on_attached_to_parent``: invoked when attached via ``attach_instance``.
- ``_describe_entry_extra``: allow subclasses to extend per-entry description.
"""

from __future__ import annotations

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
        "_entries",
        "_handlers",
        "_children",
        "_get_defaults",
        "_is_branch",
    )

    def __init__(
        self,
        owner: Any,
        name: str | None = None,
        prefix: str | None = None,
        *,
        get_default_handler: Callable | None = None,
        get_use_smartasync: bool | None = None,
        get_kwargs: dict[str, Any] | None = None,
        branch: bool = False,
        auto_discover: bool = True,
        auto_selector: str = "*",
        parent_router: BaseRouter | None = None,
    ) -> None:
        if owner is None:
            raise ValueError("Router requires a parent instance")
        self.instance = owner
        self.name = name
        self.prefix = prefix or ""
        self._is_branch = bool(branch)
        self._entries: dict[str, MethodEntry] = {}
        self._handlers: dict[str, Callable] = {}
        self._children: dict[str, BaseRouter] = {}
        defaults: dict[str, Any] = dict(get_kwargs or {})
        if get_default_handler is not None:
            defaults.setdefault("default_handler", get_default_handler)
        if get_use_smartasync is not None:
            defaults.setdefault("use_smartasync", get_use_smartasync)
        self._get_defaults: dict[str, Any] = defaults
        self._register_with_owner()
        if self._is_branch and auto_discover:
            raise ValueError("Branch routers cannot auto-discover handlers")
        if auto_discover:
            self.add_entry(auto_selector)

        # Attach to parent router if specified
        if parent_router is not None:
            alias = name
            if not alias:
                raise ValueError("Child router must have a name when using parent_router")
            if alias in parent_router._children and parent_router._children[alias] is not self:
                raise ValueError(f"Child name collision: {alias!r}")
            parent_router._children[alias] = self
            self._on_attached_to_parent(parent_router)

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

    def add_entry(
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
                self.add_entry(
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
                return self
            if "," in target:
                for chunk in target.split(","):
                    chunk = chunk.strip()
                    if chunk:
                        self.add_entry(
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
            raise TypeError(f"Unsupported add_entry target: {target!r}")

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
    # Handler execution
    # ------------------------------------------------------------------
    def _rebuild_handlers(self) -> None:
        handlers: dict[str, Callable] = {}
        for logical_name, entry in self._entries.items():
            wrapped = self._wrap_handler(entry, entry.func)
            handlers[logical_name] = wrapped
        self._handlers = handlers

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
        """
        opts = SmartOptions(options, defaults=self._get_defaults)
        default = getattr(opts, "default_handler", None)
        use_smartasync = getattr(opts, "use_smartasync", False)

        # Handle path with "/" by delegating to child routers
        if "/" in selector:
            first, rest = selector.split("/", 1)
            child = self._children.get(first)
            if child is None:
                if default is not None:
                    return default  # type: ignore[no-any-return]
                return None
            # Delegate to child router's get()
            return child.get(rest, **options)

        # Single segment: check handlers first, then children
        handler = self._handlers.get(selector)
        if handler is not None:
            if use_smartasync:
                from smartasync import smartasync  # type: ignore

                handler = smartasync(handler)
            return handler

        child_router = self._children.get(selector)
        if child_router is not None:
            return child_router

        # Nothing found - use default or return None
        if default is not None:
            return default  # type: ignore[no-any-return]

        return None

    __getitem__ = get

    def call(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        """Fetch and invoke a handler in one step."""
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
            lazy: If True, child routers are returned as callables that
                  produce their nodes when invoked, instead of recursing
                  immediately.
            mode: Output format mode (e.g., "openapi"). If None, returns
                  standard introspection format.
            **kwargs: Filter arguments passed to plugins via allow_entry().
        """
        if mode:
            handler = getattr(self, f"_mode_{mode}", self._mode_missing)
            return handler(mode=mode, basepath=basepath, lazy=lazy, **kwargs)

        if basepath:
            target = self.get(basepath)
            if not isinstance(target, BaseRouter):
                return {}
            return target.nodes(lazy=lazy, **kwargs)
        filter_args = self._prepare_filter_args(**kwargs)

        entries = {
            entry.name: self._entry_node_info(entry)
            for entry in self._entries.values()
            if self._allow_entry(entry, **filter_args)
        }

        routers: dict[str, Any]
        if lazy:
            routers = {
                child_name: (lambda c=child: c.nodes(lazy=True, **kwargs))
                for child_name, child in self._children.items()
            }
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
            "router": self,
            "instance": self.instance,
            "plugin_info": self._get_plugin_info(),
        }
        if entries:
            result["entries"] = entries
        if routers:
            result["routers"] = routers

        return result

    def _mode_missing(self, mode: str, **kwargs: Any) -> dict[str, Any]:
        """Handle unknown mode values."""
        raise ValueError(f"Unknown mode: {mode}")

    def _mode_openapi(
        self,
        basepath: str | None = None,
        lazy: bool = False,
        path_prefix: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return OpenAPI-compatible schema for this router's handlers.

        Args:
            basepath: Optional path to start from (e.g., "child/grandchild").
            lazy: If True, child routers are returned as callables.
            path_prefix: Prefix for generated paths (used internally for recursion).
            **kwargs: Filter arguments passed to plugins via allow_entry().

        Returns:
            Dict with "paths" containing OpenAPI path items, and "routers" for children.
        """
        if basepath:
            target = self.get(basepath)
            if not isinstance(target, BaseRouter):
                return {"paths": {}, "routers": {}}
            new_prefix = f"{path_prefix}/{basepath}" if path_prefix else f"/{basepath}"
            return target._mode_openapi(lazy=lazy, path_prefix=new_prefix, **kwargs)

        filter_args = self._prepare_filter_args(**kwargs)

        paths: dict[str, Any] = {}
        for entry in self._entries.values():
            if not self._allow_entry(entry, **filter_args):
                continue
            path = f"{path_prefix}/{entry.name}" if path_prefix else f"/{entry.name}"
            paths[path] = self._entry_to_openapi(entry)

        routers: dict[str, Any]
        if lazy:
            routers = {
                child_name: (
                    lambda c=child, p=path_prefix, n=child_name: c._mode_openapi(
                        lazy=True, path_prefix=f"{p}/{n}" if p else f"/{n}", **kwargs
                    )
                )
                for child_name, child in self._children.items()
            }
        else:
            for child_name, child in self._children.items():
                child_prefix = f"{path_prefix}/{child_name}" if path_prefix else f"/{child_name}"
                child_schema = child._mode_openapi(lazy=False, path_prefix=child_prefix, **kwargs)
                paths.update(child_schema.get("paths", {}))
            routers = {}

        result: dict[str, Any] = {"paths": paths}
        if routers:
            result["routers"] = routers
        return result

    def _entry_to_openapi(self, entry: MethodEntry) -> dict[str, Any]:
        """Convert a single entry to OpenAPI path item format."""
        func = entry.func
        doc = inspect.getdoc(func) or func.__doc__ or ""
        summary = doc.split("\n")[0] if doc else entry.name

        operation: dict[str, Any] = {
            "operationId": entry.name,
            "summary": summary,
        }
        if doc:
            operation["description"] = doc

        # Extract parameters from pydantic metadata if available
        pydantic_meta = entry.metadata.get("pydantic", {})
        model = pydantic_meta.get("model")
        if model and hasattr(model, "model_json_schema"):
            schema = model.model_json_schema()
            operation["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": schema}},
            }
        else:
            # Fallback: extract from type hints
            try:
                hints = get_type_hints(func)
            except Exception:
                hints = {}
            hints.pop("return", None)
            if hints:
                parameters = []
                sig = inspect.signature(func)
                for param_name, hint in hints.items():
                    param = sig.parameters.get(param_name)
                    if param is None:
                        continue
                    param_schema: dict[str, Any] = {
                        "name": param_name,
                        "in": "query",
                        "schema": {"type": self._python_type_to_openapi(hint)},
                    }
                    if param.default is inspect.Parameter.empty:
                        param_schema["required"] = True
                    else:
                        param_schema["required"] = False
                    parameters.append(param_schema)
                if parameters:
                    operation["parameters"] = parameters

        # Add return type if available
        try:
            hints = get_type_hints(func)
            return_hint = hints.get("return")
            if return_hint:
                operation["responses"] = {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {"type": self._python_type_to_openapi(return_hint)}
                            }
                        },
                    }
                }
        except Exception:
            pass

        if "responses" not in operation:
            operation["responses"] = {"200": {"description": "Successful response"}}

        return {"post": operation}

    @staticmethod
    def _python_type_to_openapi(python_type: Any) -> str:
        """Convert Python type to OpenAPI type string."""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        origin = getattr(python_type, "__origin__", None)
        if origin is not None:
            python_type = origin
        return type_map.get(python_type, "object")

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
