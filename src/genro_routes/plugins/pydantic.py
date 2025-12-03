"""Pydantic validation plugin for Genro Routes.

Automatically validates handler inputs using Pydantic type hints.

At registration time (``on_decore``), inspects handler type hints and builds
a Pydantic model capturing annotated parameters. At call time (``wrap_handler``),
validates annotated args/kwargs before calling the real handler.

Example::

    from genro_routes import Router, RoutedClass, route

    class MyService(RoutedClass):
        api = Router(name="api").plug("pydantic")

        @route("api")
        def get_user(self, user_id: int, name: str = "default"):
            return {"id": user_id, "name": name}

    svc = MyService()
    svc.api.call("get_user", user_id=123)  # OK
    svc.api.call("get_user", user_id="not_an_int")  # ValidationError

Configuration::

    # Disable validation for a specific handler
    @route("api", pydantic_disabled=True)
    def unvalidated_handler(self):
        pass
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, get_type_hints

try:
    from pydantic import ValidationError, create_model
except ImportError as err:  # pragma: no cover - import guard
    raise ImportError(
        "Pydantic plugin requires pydantic. Install with: pip install genro-routes[pydantic]"
    ) from err

from genro_routes.core.router import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry

if TYPE_CHECKING:
    from genro_routes.core import Router


class PydanticPlugin(BasePlugin):
    """Validate handler inputs with Pydantic using type hints.

    Builds a validation model from function type hints at registration time
    and validates all annotated parameters at call time.
    """

    plugin_code = "pydantic"
    plugin_description = "Validates handler inputs using Pydantic type hints"

    def __init__(self, router, **config: Any):
        super().__init__(router, **config)

    def configure(self, disabled: bool = False):  # type: ignore[override]
        """Configure pydantic plugin options.

        Args:
            disabled: If True, skip validation for this handler/router.
        """
        pass  # Storage is handled by the wrapper

    def on_decore(self, route: Router, func: Callable, entry: MethodEntry) -> None:
        """Build Pydantic model from handler type hints."""
        try:
            hints = get_type_hints(func)
        except Exception:
            # No hints resolvable, no model created
            return

        hints.pop("return", None)
        if not hints:
            # No parameter hints, no model needed
            return

        sig = inspect.signature(func)
        fields = {}
        for param_name, hint in hints.items():
            param = sig.parameters.get(param_name)
            if param is None:
                raise ValueError(
                    f"Handler '{func.__name__}' has type hint for '{param_name}' "
                    f"which is not in the function signature"
                )
            elif param.default is inspect.Parameter.empty:
                fields[param_name] = (hint, ...)
            else:
                fields[param_name] = (hint, param.default)

        validation_model = create_model(f"{func.__name__}_Model", **fields)  # type: ignore

        entry.metadata["pydantic"] = {
            "model": validation_model,
            "hints": hints,
            "signature": sig,
        }

    def wrap_handler(self, route: Router, entry: MethodEntry, call_next: Callable):
        """Validate annotated parameters with the cached Pydantic model before calling."""
        meta = entry.metadata.get("pydantic", {})
        model = meta.get("model")
        if not model:
            # No model created (no type hints), passthrough
            return call_next

        sig = meta["signature"]
        hints = meta["hints"]

        def wrapper(*args, **kwargs):
            # Check disabled config at runtime (not at wrap time)
            cfg = self.configuration(entry.name)
            if cfg.get("disabled"):
                return call_next(*args, **kwargs)

            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            args_to_validate = {k: v for k, v in bound.arguments.items() if k in hints}
            other_args = {k: v for k, v in bound.arguments.items() if k not in hints}
            try:
                validated = model(**args_to_validate)
            except ValidationError as exc:
                raise ValidationError.from_exception_data(
                    title=f"Validation error in {entry.name}",
                    line_errors=exc.errors(),
                ) from exc

            final_args = other_args.copy()
            for key, value in validated:
                final_args[key] = value
            return call_next(**final_args)

        return wrapper

    def get_model(self, entry: MethodEntry) -> tuple[str, Any] | None:
        """Return the Pydantic model for this handler if not disabled."""
        cfg = self.configuration(entry.name)
        if cfg.get("disabled"):
            return None

        meta = entry.metadata.get("pydantic", {})
        model = meta.get("model")
        if not model:
            return None
        return ("pydantic_model", model)

    def entry_metadata(self, router: Any, entry: MethodEntry) -> dict[str, Any]:
        """Return pydantic metadata for introspection."""
        meta = entry.metadata.get("pydantic", {})
        if not meta:
            return {}
        return {
            "model": meta.get("model"),
            "hints": meta.get("hints"),
        }


Router.register_plugin(PydanticPlugin)
