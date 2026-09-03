"""Pydantic validation and response schema plugin for Genro Routes.

Validates handler inputs using Pydantic type hints and generates JSON Schema
from return type annotations for bridge consumption (MCP, OpenAPI).

At registration time (``on_decore``):
- Inspects parameter type hints and builds a Pydantic model for input validation.
- Inspects return type annotation and generates a JSON Schema via ``TypeAdapter``,
  stored in ``entry.metadata["pydantic"]["response_schema"]``.

At call time (``wrap_handler``), validates annotated args/kwargs before calling
the real handler.

Strict by default
-----------------
Validation runs in strict mode: an argument must already have the annotated
type. ``"12"`` for an ``int`` parameter is a ``ValidationError``, not a
conversion. Pydantic's own strict-mode allowances still apply (an ``int`` is
accepted for a ``float`` parameter).

Coercion is opt-in per call, with the reserved keyword ``_coerce=True`` passed
to ``RouterNode.__call__``. It applies to every parameter of that call:
``"12"`` becomes ``12``, ``"2026-09-01"`` becomes a ``date``. ``_coerce`` is
always consumed by the router and by this plugin's wrapper, and never reaches
the handler.

``_coerce=True`` on a router without the ``pydantic`` plugin raises the
exception mapped to the ``not_available`` error code. ``_coerce=True`` on an
entry with no type hints (no model) or with validation disabled is silently
ignored: there is nothing to convert.

A single parameter can opt out of strict mode regardless of ``_coerce``, with
``Annotated[int, Field(strict=False)]``: the per-field setting overrides the
model-level strict flag.

Example::

    from typing import TypedDict
    from genro_routes import Router, RoutingClass, route

    class UserResponse(TypedDict):
        id: int
        name: str

    class MyService(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def get_user(self, user_id: int) -> UserResponse:
            return {"id": user_id, "name": "alice"}

    svc = MyService()
    svc.route.node("get_user")(user_id=123)  # OK, validated
    svc.route.node("get_user")(user_id="123")  # ValidationError (strict)
    svc.route.node("get_user")(user_id="123", _coerce=True)  # OK, converted
    svc.route.node("get_user")(user_id="not_an_int")  # ValidationError

    # Response schema available in metadata
    entry = svc.route._entries["get_user"]
    entry.metadata["pydantic"]["response_schema"]
    # {"type": "object", "properties": {"id": ..., "name": ...}, ...}

Configuration::

    # Disable validation for a specific handler
    @route(pydantic_disabled=True)
    def unvalidated_handler(self):
        pass
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, get_type_hints

try:
    from pydantic import ConfigDict, TypeAdapter, ValidationError, create_model
except ImportError as err:  # pragma: no cover - import guard
    raise ImportError(
        "Pydantic plugin requires pydantic. Install with: pip install genro-routes[pydantic]"
    ) from err

from genro_routes.core.router import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry

if TYPE_CHECKING:
    from genro_routes.core import Router


class PydanticPlugin(BasePlugin):
    """Validate handler inputs and generate response schemas with Pydantic.

    At registration time (``on_decore``), builds a Pydantic model from parameter
    type hints for input validation, and generates a JSON Schema from the return
    type annotation via ``TypeAdapter`` for bridge consumption.

    Behavior:
        - Only annotated parameters are validated
        - Unannotated parameters pass through unchanged
        - Validation is strict: no type coercion unless the call passes
          ``_coerce=True``, which converts every parameter of that call
        - ``Annotated[T, Field(strict=False)]`` opts a single parameter out of
          strict mode without ``_coerce``
        - ValidationError is raised on invalid input
        - Return type annotations produce ``response_schema`` in metadata
        - Can be disabled per-handler via ``pydantic_disabled=True``

    Configuration options:
        - ``disabled``: Skip validation for this handler/router (default False)

    Attributes:
        plugin_code: "pydantic" - used for registration and config prefix.
        plugin_description: Human-readable description.

    Example:
        Basic usage::

            class MyService(RoutingClass):
                def __init__(self):
                    self.route.plug("pydantic")

                @route()
                def get_user(self, user_id: int) -> dict[str, int]:
                    return {"id": user_id}

            svc = MyService()
            svc.route.node("get_user")(user_id=123)           # OK
            svc.route.node("get_user")(user_id="123")         # ValidationError
            svc.route.node("get_user")(user_id="123", _coerce=True)  # OK -> 123
            svc.route.node("get_user")(user_id="not_an_int")  # ValidationError

            # Response schema in metadata
            svc.route._entries["get_user"].metadata["pydantic"]["response_schema"]

        Disable validation::

            @route(pydantic_disabled=True)
            def unvalidated(self, data):
                return data  # no validation
    """

    plugin_code = "pydantic"
    plugin_description = "Validates inputs and generates response schemas using Pydantic"

    def __init__(self, router, **config: Any):
        super().__init__(router, **config)

    def configure(self, disabled: bool = False):  # type: ignore[override]
        """Configure pydantic plugin options.

        Args:
            disabled: If True, skip validation for this handler/router.
        """
        pass  # Storage is handled by the wrapper

    def on_decore(self, route: Router, func: Callable, entry: MethodEntry) -> None:
        """Build Pydantic model from handler type hints and generate response schema."""
        # Always capture signature info (even without type hints)
        sig = inspect.signature(func)
        accepts_varargs = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL
            for p in sig.parameters.values()
        )

        try:
            hints = get_type_hints(func, include_extras=True)
        except Exception:
            hints = {}

        return_hint = hints.pop("return", None)

        # Always save signature metadata
        pydantic_meta: dict[str, Any] = {
            "signature": sig,
            "accepts_varargs": accepts_varargs,
            "hints": hints,
        }

        if return_hint is not None:
            pydantic_meta["return_type"] = return_hint
            try:
                adapter = TypeAdapter(return_hint)
                pydantic_meta["response_schema"] = adapter.json_schema()
            except Exception:
                pass

        if hints:
            # Build validation model only if we have hints
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

            # strict=True on the model config: no coercion unless a call asks
            # for it. A field declaring Field(strict=False) still overrides it.
            pydantic_meta["model"] = create_model(  # type: ignore[call-overload]
                f"{func.__name__}_Model",
                __config__=ConfigDict(strict=True),
                **fields,
            )

        # Cache the neutral input-params description once (read by nodes()/node().
        # params). The heavy model_json_schema() must never run per-call.
        model = pydantic_meta.get("model")
        props: dict[str, Any] = {}
        if model is not None:
            request_schema = model.model_json_schema()
            props = request_schema.get("properties", {})
            pydantic_meta["request_schema"] = request_schema
        # fields is the complete parameter description, in declaration order,
        # including the var-parameters (*args -> var_positional, **kwargs ->
        # var_keyword) so a consumer knows the handler accepts arbitrary
        # positional/keyword arguments without re-inspecting the callable.
        var_kinds = (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
        param_fields = []
        for param_name, param in sig.parameters.items():
            if param.kind in var_kinds:
                param_fields.append(
                    {
                        "name": param_name,
                        "schema": None,
                        "required": False,
                        "default": None,
                        "kind": param.kind.name.lower(),
                    }
                )
                continue
            required = param.default is inspect.Parameter.empty
            param_fields.append(
                {
                    "name": param_name,
                    "schema": props.get(param_name),
                    "required": required,
                    "default": None if required else param.default,
                    "kind": param.kind.name.lower(),
                }
            )
        pydantic_meta["param_fields"] = param_fields

        entry.metadata["pydantic"] = pydantic_meta

    def wrap_handler(self, route: Router, entry: MethodEntry, call_next: Callable):
        """Validate annotated parameters with the cached Pydantic model before calling.

        The wrapper is installed even for an entry without a model, because it
        owns the reserved ``_coerce`` keyword: it must consume it in every case
        so the handler never sees it. With a model, ``_coerce`` selects lax
        validation for this call; without one there is nothing to convert and
        the keyword is simply dropped.
        """
        meta = entry.metadata.get("pydantic", {})
        model = meta.get("model")
        sig = meta.get("signature")
        hints = meta.get("hints", {})

        def wrapper(*args, **kwargs):
            coerce = bool(kwargs.pop("_coerce", False))
            # Check disabled config at runtime (not at wrap time)
            cfg = self.configuration(entry.name)
            if not model or cfg.get("disabled"):
                return call_next(*args, **kwargs)

            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            args_to_validate = {k: v for k, v in bound.arguments.items() if k in hints}
            other_args = {k: v for k, v in bound.arguments.items() if k not in hints}
            try:
                # strict=None defers to the model config (strict); coercion
                # opts this single call out of it.
                validated = model.model_validate(
                    args_to_validate, strict=False if coerce else None
                )
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
        """Return the Pydantic model for this handler if not disabled.

        Args:
            entry: The MethodEntry to get the model for.

        Returns:
            Tuple of ("pydantic_model", model_class) if available, else None.
        """
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
        result: dict[str, Any] = {
            "model": meta.get("model"),
            "hints": meta.get("hints"),
            "accepts_varargs": meta.get("accepts_varargs", False),
        }
        response_schema = meta.get("response_schema")
        if response_schema is not None:
            result["response_schema"] = response_schema
        return result


Router.register_plugin(PydanticPlugin)
