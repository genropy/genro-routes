# Copyright 2025 Softwell S.r.l. — Apache License 2.0
"""Mapping from Python type annotations to click parameter types."""

import enum
import inspect
import json
from typing import Any, Literal, Union, get_args, get_origin

import click

# Direct mapping: Python type → click.ParamType
_SIMPLE_MAP: dict[type, click.ParamType] = {
    str: click.STRING,
    int: click.INT,
    float: click.FLOAT,
    bool: click.BOOL,
}


class ParamConverter:
    """Converts handler signature parameters to click parameters."""

    def to_click_params(self, func: Any) -> list[click.Parameter]:
        """Extract click parameters from a callable's signature.

        Parameters without default become click.Argument (positional).
        Parameters with default become click.Option.
        ``self`` is skipped automatically.
        """
        sig = inspect.signature(func)
        try:
            from typing import get_type_hints

            hints = get_type_hints(func, include_extras=True)
        except Exception:
            hints = {}
        hints.pop("return", None)

        params: list[click.Parameter] = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            hint = hints.get(name)
            has_default = param.default is not inspect.Parameter.empty
            click_param = self._make_param(name, hint, param.default, has_default)
            params.append(click_param)

        return params

    def _make_param(
        self,
        name: str,
        hint: type | None,
        default: Any,
        has_default: bool,
    ) -> click.Parameter:
        """Build a single click.Argument or click.Option."""
        click_type, is_multiple, is_flag = self._resolve_type(hint)
        cli_name = name.replace("_", "-")

        if is_flag:
            return click.Option(
                [f"--{cli_name}/--no-{cli_name}"],
                default=default if has_default else False,
                help=f"({_type_label(hint)})",
            )

        if is_multiple:
            return click.Option(
                [f"--{cli_name}"],
                type=click_type,
                multiple=True,
                default=default if has_default else (),
                help=f"({_type_label(hint)})",
            )

        if not has_default:
            return click.Argument([name], type=click_type)

        return click.Option(
            [f"--{cli_name}"],
            type=click_type,
            default=default,
            show_default=True,
            help=f"({_type_label(hint)})" if hint else None,
        )

    def _resolve_type(
        self, hint: type | None
    ) -> tuple[click.ParamType, bool, bool]:
        """Return (click_type, is_multiple, is_flag)."""
        if hint is None:
            return click.STRING, False, False

        # Unwrap Optional[X] → X
        origin = get_origin(hint)
        if origin is Union:
            args = [a for a in get_args(hint) if a is not type(None)]
            if len(args) == 1:
                return self._resolve_type(args[0])

        # bool → flag
        if hint is bool:
            return click.BOOL, False, True

        # Simple types
        if hint in _SIMPLE_MAP:
            return _SIMPLE_MAP[hint], False, False

        # Literal["a", "b"] → Choice
        if origin is Literal:
            choices = [str(v) for v in get_args(hint)]
            return click.Choice(choices), False, False

        # Enum → Choice
        if isinstance(hint, type) and issubclass(hint, enum.Enum):
            choices = [m.name for m in hint]
            return click.Choice(choices), False, False

        # list[X] → multiple
        if origin is list:
            inner_args = get_args(hint)
            inner = inner_args[0] if inner_args else str
            inner_type = _SIMPLE_MAP.get(inner, click.STRING)
            return inner_type, True, False

        # dict, complex types → JSON string
        return click.STRING, False, False


class JsonParamType(click.ParamType):
    """Click type that parses a JSON string into a Python object."""

    name = "JSON"

    def convert(self, value: Any, param: Any, ctx: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            self.fail(f"Invalid JSON: {exc}", param, ctx)


JSON = JsonParamType()


def _type_label(hint: type | None) -> str:
    """Human-readable label for a type hint."""
    if hint is None:
        return "str"
    if hasattr(hint, "__name__"):
        return hint.__name__
    return str(hint)
