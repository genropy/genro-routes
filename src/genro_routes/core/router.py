"""Router with plugin pipeline for Genro Routes.

``Router`` extends ``BaseRouter`` with a global plugin registry, per-router
plugin instances, middleware wrapping, and plugin state stored on the router.

Internal state
--------------
- ``_plugin_specs``: list of ``_PluginSpec`` (factory, kwargs copy).
- ``_plugins``: instantiated plugins in the order they were attached.
- ``_plugins_by_name``: name → plugin instance (first wins).
- ``_inherited_from``: set of parent ids already inherited to avoid double
  cloning when the same child is attached multiple times.
- ``_plugin_info``: per-plugin state store on the router.

Global registry
---------------
``Router.register_plugin(name, plugin_class)`` validates that ``plugin_class``
is a subclass of ``BasePlugin`` and ``name`` is non-empty.

Attaching plugins
-----------------
``plug(plugin_name, **config)`` looks up the plugin class by name in the global
registry. It stores a ``_PluginSpec``, instantiates the plugin, appends to
``_plugins`` and ``_plugins_by_name``, applies ``plugin.on_decore`` to all
existing entries, rebuilds handlers, and returns ``self``.

Wrapping pipeline
-----------------
``_wrap_handler(entry, call_next)`` builds middleware layers from the current
``_plugins`` in reverse order (last attached closest to the handler).

Inheritance behaviour
---------------------
``_on_attached_to_parent(parent)`` runs when a child router is attached.
Parent specs are cloned once per parent. Cloned specs are instantiated into
new plugins that are prepended ahead of existing child plugins.

Example::

    from genro_routes import Router, RoutingClass, route

    class MyService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def hello(self):
            return "Hello!"
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from genro_toolbox import dictExtract

from genro_routes.core.base_router import BaseRouter
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry

__all__ = ["Router"]

_PLUGIN_REGISTRY: dict[str, type[BasePlugin]] = {}


@dataclass
class _PluginSpec:
    """Specification for creating plugin instances."""

    factory: type[BasePlugin]
    kwargs: dict[str, Any]

    def instantiate(self, router: Router) -> BasePlugin:
        """Create a plugin instance for the given router."""
        return self.factory(router=router, **self.kwargs)

    def clone(self) -> _PluginSpec:
        """Return a copy with shallow-copied kwargs."""
        return _PluginSpec(self.factory, dict(self.kwargs))


class Router(BaseRouter):
    """Router with plugin registry and pipeline support.

    Extends BaseRouter with:
        - Global plugin registry for registering plugin classes
        - Per-router plugin instances with middleware wrapping
        - Plugin state management and configuration
        - Plugin inheritance when attaching child routers
    """

    __slots__ = BaseRouter.__slots__ + (
        "_plugin_specs",
        "_plugins",
        "_plugins_by_name",
        "_inherited_from",
        "_plugin_info",
        "_plugin_children",
    )

    def __init__(self, *args, **kwargs):
        self._plugin_specs: list[_PluginSpec] = []
        self._plugins: list[BasePlugin] = []
        self._plugins_by_name: dict[str, BasePlugin] = {}
        self._inherited_from: set[int] = set()
        self._plugin_info: dict[str, dict[str, Any]] = {}
        self._plugin_children: dict[str, list[Router]] = {}  # plugin_name -> [child routers]
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Plugin registration
    # ------------------------------------------------------------------
    @classmethod
    def register_plugin(cls, plugin_class: type[BasePlugin], name: str | None = None) -> None:
        """Register a plugin class globally.

        Args:
            plugin_class: A BasePlugin subclass with plugin_code defined.
            name: Optional override name. If provided, overwrites any existing
                  registration. If not provided, uses plugin_code and raises
                  if already registered with a different class.

        Raises:
            TypeError: If plugin_class is not a BasePlugin subclass.
            ValueError: If plugin_code is missing or name collision occurs.
        """
        if not isinstance(plugin_class, type) or not issubclass(plugin_class, BasePlugin):
            raise TypeError("plugin_class must be a BasePlugin subclass")
        if not getattr(plugin_class, "plugin_code", None):
            raise ValueError(
                f"Plugin {plugin_class.__name__} not following standards: missing plugin_code"
            )
        code = name or plugin_class.plugin_code
        # If name is explicitly provided, allow overwrite (intentional replacement)
        # Otherwise, reject collision
        if name is None:
            existing = _PLUGIN_REGISTRY.get(code)
            if existing is not None and existing is not plugin_class:
                raise ValueError(f"Plugin '{code}' already registered")
        _PLUGIN_REGISTRY[code] = plugin_class

    @classmethod
    def available_plugins(cls) -> dict[str, type[BasePlugin]]:
        """Return a copy of the global plugin registry."""
        return dict(_PLUGIN_REGISTRY)

    def plug(self, plugin: str, **config: Any) -> Router:
        """Attach a plugin by name (previously registered globally).

        Args:
            plugin: Name of the plugin to attach.
            **config: Configuration options passed to the plugin.

        Returns:
            self (for method chaining).

        Raises:
            TypeError: If plugin is not a string.
            ValueError: If plugin is not registered or already attached.
        """
        if not isinstance(plugin, str):
            raise TypeError(
                f"Plugin must be referenced by name string, got {type(plugin).__name__}"
            )
        plugin_class = _PLUGIN_REGISTRY.get(plugin)
        if plugin_class is None:
            available = ", ".join(sorted(_PLUGIN_REGISTRY)) or "none"
            raise ValueError(
                f"Unknown plugin '{plugin}'. Register it first. Available plugins: {available}"
            )
        if plugin in self._plugins_by_name:
            raise ValueError(
                f"Plugin '{plugin}' is already attached to this router. "
                "Use configure() to update settings."
            )
        spec_kwargs = dict(config)
        spec = _PluginSpec(plugin_class, spec_kwargs)
        self._plugin_specs.append(spec)
        instance = spec.instantiate(self)
        self._plugins.append(instance)
        self._plugins_by_name[instance.name] = instance
        # Plugin will be applied to entries during lazy binding (_bind)
        # If already bound, apply now
        if self._bound:
            self._apply_plugin_to_entries(instance)
            self._rebuild_handlers()
        return self

    def iter_plugins(self) -> list[BasePlugin]:  # type: ignore[override]
        """Return attached plugin instances in application order."""
        return list(self._plugins)

    def get_config(self, plugin_name: str, method_name: str | None = None) -> dict[str, Any]:
        """Return plugin config (global + per-handler overrides) for an attached plugin."""
        plugin = self._plugins_by_name.get(plugin_name)
        if plugin is None:
            raise AttributeError(
                f"No plugin named '{plugin_name}' attached to router '{self.name}'"
            )
        return plugin.configuration(method_name)

    def __getattr__(self, name: str) -> Any:
        plugin = self._plugins_by_name.get(name)
        if plugin is None:
            raise AttributeError(f"No plugin named '{name}' attached to router '{self.name}'")
        return plugin

    def _get_plugin_bucket(self, plugin_name: str, create: bool = False) -> dict[str, Any] | None:
        bucket = self._plugin_info.get(plugin_name)
        if bucket is None and create:
            bucket = {"_all_": {"config": {}, "locals": {}}}
            self._plugin_info[plugin_name] = bucket
        if bucket is not None and "_all_" not in bucket:
            bucket["_all_"] = {"config": {}, "locals": {}}
        return bucket

    # ------------------------------------------------------------------
    # Runtime helpers (state stored on plugin_info)
    # ------------------------------------------------------------------
    def set_plugin_enabled(self, method_name: str, plugin_name: str, enabled: bool = True) -> None:
        """Enable or disable a plugin for a specific handler."""
        bucket = self._get_plugin_bucket(plugin_name, create=False)
        if bucket is None:
            raise AttributeError(
                f"No plugin named '{plugin_name}' attached to router '{self.name}'"
            )
        entry = bucket.setdefault(method_name, {"config": {}, "locals": {}})
        entry.setdefault("locals", {})["enabled"] = bool(enabled)

    def is_plugin_enabled(self, method_name: str, plugin_name: str) -> bool:
        """Check if a plugin is enabled for a specific handler.

        Resolution order (first found wins):
        1. entry locals (runtime override via set_plugin_enabled)
        2. entry config (static via configure(_target=method_name, enabled=...))
        3. global locals (runtime override via set_plugin_enabled for _all_)
        4. global config (static via configure(enabled=...))
        5. default: True
        """
        bucket = self._get_plugin_bucket(plugin_name, create=False)
        if bucket is None:
            raise AttributeError(
                f"No plugin named '{plugin_name}' attached to router '{self.name}'"
            )
        # Check entry-level first
        entry_data = bucket.get(method_name, {})
        if "enabled" in entry_data.get("locals", {}):
            return bool(entry_data["locals"]["enabled"])
        if "enabled" in entry_data.get("config", {}):
            return bool(entry_data["config"]["enabled"])
        # Then check global (_all_)
        base_data = bucket.get("_all_", {})
        if "enabled" in base_data.get("locals", {}):
            return bool(base_data["locals"]["enabled"])
        if "enabled" in base_data.get("config", {}):
            return bool(base_data["config"]["enabled"])
        return True

    def set_runtime_data(self, method_name: str, plugin_name: str, key: str, value: Any) -> None:
        """Set runtime data for a plugin/handler combination."""
        bucket = self._get_plugin_bucket(plugin_name, create=False)
        if bucket is None:
            raise AttributeError(
                f"No plugin named '{plugin_name}' attached to router '{self.name}'"
            )
        entry = bucket.setdefault(method_name, {"config": {}, "locals": {}})
        entry.setdefault("locals", {})[key] = value

    def get_runtime_data(
        self, method_name: str, plugin_name: str, key: str, default: Any = None
    ) -> Any:
        """Get runtime data for a plugin/handler combination."""
        bucket = self._get_plugin_bucket(plugin_name, create=False)
        if bucket is None:
            raise AttributeError(
                f"No plugin named '{plugin_name}' attached to router '{self.name}'"
            )
        entry_locals = bucket.get(method_name, {}).get("locals", {})
        return entry_locals.get(key, default)

    # ------------------------------------------------------------------
    # Overrides/hooks
    # ------------------------------------------------------------------
    def _wrap_handler(self, entry: MethodEntry, call_next: Callable) -> Callable:  # type: ignore[override]
        wrapped = call_next
        for plugin in reversed(self._plugins):
            plugin_call = plugin.wrap_handler(self, entry, wrapped)
            wrapped = self._create_wrapper(plugin, entry, plugin_call, wrapped)
        return wrapped

    def _create_wrapper(
        self,
        plugin: BasePlugin,
        entry: MethodEntry,
        plugin_call: Callable,
        next_handler: Callable,
    ) -> Callable:
        @wraps(next_handler)
        def wrapper(*args, **kwargs):
            if not self.is_plugin_enabled(entry.name, plugin.name):
                return next_handler(*args, **kwargs)
            return plugin_call(*args, **kwargs)

        return wrapper

    def _apply_plugin_to_entries(self, plugin: BasePlugin) -> None:
        # Access raw dict to avoid triggering lazy binding
        for entry in self._BaseRouter__entries_raw.values():  # type: ignore[attr-defined]
            if plugin.name not in entry.plugins:
                entry.plugins.append(plugin.name)
            plugin.on_decore(self, entry.func, entry)

    def _on_attached_to_parent(self, parent: Router) -> None:  # type: ignore[override]
        parent_id = id(parent)
        if parent_id in self._inherited_from:
            return
        self._inherited_from.add(parent_id)

        inherited_plugins = []
        for parent_plugin in parent._plugins:
            if parent_plugin.name not in self._plugins_by_name:
                # Child doesn't have this plugin - create new instance and inherit
                child_plugin = parent_plugin.__class__(self)
                # Register child in parent's notification list
                parent._plugin_children.setdefault(parent_plugin.name, []).append(self)
                # Add to child's plugin registry
                self._plugins_by_name[parent_plugin.name] = child_plugin
                self._plugins.append(child_plugin)
                inherited_plugins.append((child_plugin, parent_plugin))
            else:
                # Child already has this plugin - let it handle inheritance
                child_plugin = self._plugins_by_name[parent_plugin.name]
                # Register for notifications even if child has its own plugin
                parent._plugin_children.setdefault(parent_plugin.name, []).append(self)
                # Call hook to let plugin decide what to do
                child_plugin.on_attached_to_parent(parent_plugin)

        # For inherited plugins: call hook and apply on_decore
        for child_plugin, parent_plugin in inherited_plugins:
            child_plugin.on_attached_to_parent(parent_plugin)
            for entry in self._entries.values():
                if child_plugin.name not in entry.plugins:
                    entry.plugins.append(child_plugin.name)
                child_plugin.on_decore(self, entry.func, entry)

        if inherited_plugins:
            self._rebuild_handlers()

    def _after_entry_registered(self, entry: MethodEntry) -> None:  # type: ignore[override]
        for pname, cfg in entry.metadata.get("plugin_config", {}).items():
            plugin = self._plugins_by_name.get(pname)
            if plugin:
                plugin.configure(_target=entry.name, **cfg)
            else:
                bucket = self._plugin_info.setdefault(
                    pname, {"_all_": {"config": {}, "locals": {}}}
                )
                bucket.setdefault(entry.name, {"config": {}, "locals": {}})["config"].update(cfg)
        for plugin in self._plugins:
            if plugin.name not in entry.plugins:
                entry.plugins.append(plugin.name)
            plugin.on_decore(self, entry.func, entry)

    def _entry_invalid_reason(self, entry: MethodEntry | None, **allowing_args: Any) -> str:
        if entry is None:
            return "not_found"
        # Filter out None and False values
        allowing_args = {k: v for k, v in allowing_args.items() if v not in (None, False)}
        for plugin in self._plugins:
            # Extract kwargs for this specific plugin using its plugin_code prefix
            plugin_kwargs = dictExtract(
                allowing_args, f"{plugin.plugin_code}_", slice_prefix=True, pop=False
            )
            # Always consult plugin - it decides based on entry rules and user kwargs
            result = plugin.allow_entry(entry, **plugin_kwargs)
            if result:
                return result
        return ""

    def _describe_entry_extra(  # type: ignore[override]
        self, entry: MethodEntry, base_description: dict[str, Any]
    ) -> dict[str, Any]:
        """Gather plugin config and metadata for a handler."""
        plugins_info: dict[str, dict[str, Any]] = {}
        for plugin in self._plugins:
            plugin_data: dict[str, Any] = {}
            # Get config for this entry
            config = plugin.configuration(entry.name)
            if config:
                plugin_data["config"] = config
            # Get metadata from plugin
            meta = plugin.entry_metadata(self, entry)
            if meta:
                if not isinstance(meta, dict):
                    raise TypeError(  # pragma: no cover - defensive guard
                        f"Plugin {plugin.name} returned non-dict "
                        f"from entry_metadata: {type(meta)}"
                    )
                plugin_data["metadata"] = meta
            # Only include plugin if it has data
            if plugin_data:
                plugins_info[plugin.name] = plugin_data
        if plugins_info:
            return {"plugins": plugins_info}
        return {}
