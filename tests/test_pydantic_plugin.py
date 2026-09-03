# Copyright 2025-2026 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the Pydantic plugin."""

from datetime import date
from typing import Annotated

import pytest
from pydantic import Field, ValidationError

# Import to trigger plugin registration
import genro_routes.plugins.pydantic  # noqa: F401
from genro_routes import NotAvailable, RoutingClass, route


class ValidateService(RoutingClass):
    def __init__(self):
        self.calls = 0
        self.route.plug("pydantic")

    @route()
    def concat(self, text: str, number: int = 1) -> str:
        self.calls += 1
        return f"{text}:{number}"


def test_pydantic_plugin_accepts_valid_input():
    svc = ValidateService()
    assert svc.route.node("concat")("hello", 3) == "hello:3"
    # default value still works
    assert svc.route.node("concat")("hi") == "hi:1"
    assert svc.calls == 2


def test_pydantic_plugin_rejects_invalid_input():
    svc = ValidateService()
    with pytest.raises(ValidationError):
        svc.route.node("concat")(123, "oops")


def test_pydantic_plugin_disabled_at_runtime():
    """Test disabling pydantic validation at runtime via configure()."""
    svc = ValidateService()

    # First verify validation is active
    with pytest.raises(ValidationError):
        svc.route.node("concat")(123, "oops")

    # Disable validation at runtime
    svc.route.pydantic.configure(disabled=True)

    # Now invalid input passes through (no validation)
    result = svc.route.node("concat")(123, "oops")
    assert result == "123:oops"


def test_pydantic_plugin_disabled_per_handler():
    """Test disabling pydantic validation for a specific handler."""

    class MultiService(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def strict(self, text: str, number: int) -> str:
            return f"{text}:{number}"

        @route()
        def lenient(self, text: str, number: int) -> str:
            return f"{text}:{number}"

    svc = MultiService()

    # Disable only for "lenient" handler
    svc.route.pydantic.configure(_target="lenient", disabled=True)

    # "strict" still validates
    with pytest.raises(ValidationError):
        svc.route.node("strict")(123, "oops")

    # "lenient" bypasses validation
    result = svc.route.node("lenient")(123, "oops")
    assert result == "123:oops"


def test_pydantic_plugin_config_merge_base_and_handler():
    """Test that per-handler config overrides base config."""

    class MergeService(RoutingClass):
        def __init__(self):
            self.route.plug("pydantic")

        @route()
        def handler_a(self, text: str, number: int) -> str:
            return f"{text}:{number}"

        @route()
        def handler_b(self, text: str, number: int) -> str:
            return f"{text}:{number}"

    svc = MergeService()

    # Disable validation globally (base config)
    svc.route.pydantic.configure(disabled=True)

    # Both handlers should bypass validation now
    assert svc.route.node("handler_a")(123, "oops") == "123:oops"
    assert svc.route.node("handler_b")(123, "oops") == "123:oops"

    # Re-enable validation only for handler_a (per-handler overrides base)
    svc.route.pydantic.configure(_target="handler_a", disabled=False)

    # handler_a validates again, handler_b still disabled
    with pytest.raises(ValidationError):
        svc.route.node("handler_a")(123, "oops")

    assert svc.route.node("handler_b")(123, "oops") == "123:oops"


class BadArgError(Exception):
    """Custom exception used to check the unified bad-argument contract."""

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(selector)


def test_binding_error_maps_to_signature_error_with_pydantic():
    """Extra positional args (TypeError from sig.bind) map to signature_error."""
    svc = ValidateService()
    node = svc.route.node("concat", errors={"signature_error": BadArgError})
    with pytest.raises(BadArgError):
        node("a", 1, "extra")  # too many positional args for concat(text, number)


def test_binding_error_unknown_keyword_maps_to_signature_error():
    """An unexpected keyword (TypeError from sig.bind) maps to signature_error."""
    svc = ValidateService()
    node = svc.route.node("concat", errors={"signature_error": BadArgError})
    with pytest.raises(BadArgError):
        node("a", nope=1)  # 'nope' is not a parameter of concat


def test_binding_error_maps_without_pydantic():
    """Without the pydantic plugin, the binding failure maps too."""

    class PlainService(RoutingClass):
        @route()
        def concat(self, text: str, number: int = 1) -> str:
            return f"{text}:{number}"

    svc = PlainService()
    node = svc.route.node("concat", errors={"signature_error": BadArgError})
    with pytest.raises(BadArgError):
        node("a", 1, "extra")


def test_binding_error_ignores_validation_error_mapping():
    """A binding failure is not a validation_error: mapping only that code is inert."""
    svc = ValidateService()
    node = svc.route.node("concat", errors={"validation_error": BadArgError})
    with pytest.raises(TypeError):
        node("a", 1, "extra")


def test_binding_error_propagates_typeerror_without_custom():
    """With no custom exception registered, the TypeError propagates unchanged."""
    svc = ValidateService()
    with pytest.raises(TypeError):
        svc.route.node("concat")("a", 1, "extra")


# ----------------------------------------------------------------------
# Strict validation by default, coercion opt-in per call with _coerce
# ----------------------------------------------------------------------


class CoerceService(RoutingClass):
    def __init__(self):
        self.route.plug("pydantic")

    @route()
    def count(self, number: int) -> int:
        return number

    @route()
    def when(self, day: date) -> date:
        return day

    @route()
    def ratio(self, value: float) -> float:
        return value

    @route()
    def lax_number(self, number: Annotated[int, Field(strict=False)]) -> int:
        return number

    @route()
    def untyped(self, **kwargs):
        return kwargs

    @route(pydantic_disabled=True)
    def unvalidated(self, number: int) -> int:
        return number


class NotAvailableHere(Exception):
    """Custom exception mapped to the not_available error code."""

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(selector)


def test_strict_by_default_rejects_convertible_string():
    """A string is not an int: strict mode refuses it instead of converting."""
    svc = CoerceService()
    with pytest.raises(ValidationError):
        svc.route.node("count")("12")


def test_strict_by_default_accepts_exact_type():
    svc = CoerceService()
    assert svc.route.node("count")(12) == 12


def test_strict_error_maps_to_custom_validation_error():
    """The strict refusal follows the existing validation_error contract."""
    svc = CoerceService()
    node = svc.route.node("count", errors={"validation_error": BadArgError})
    with pytest.raises(BadArgError):
        node("12")


def test_coerce_converts_string_to_int():
    svc = CoerceService()
    assert svc.route.node("count")("12", _coerce=True) == 12


def test_coerce_converts_string_to_date():
    svc = CoerceService()
    assert svc.route.node("when")("2026-09-01", _coerce=True) == date(2026, 9, 1)


def test_coerce_without_pydantic_plugin_raises_not_available():
    """Coercion needs the pydantic plugin: without it the call is refused."""

    class PlainService(RoutingClass):
        @route()
        def count(self, number: int) -> int:
            return number

    svc = PlainService()
    with pytest.raises(NotAvailable):
        svc.route.node("count")(12, _coerce=True)


def test_coerce_without_pydantic_plugin_uses_custom_exception():
    class PlainService(RoutingClass):
        @route()
        def count(self, number: int) -> int:
            return number

    svc = PlainService()
    node = svc.route.node("count", errors={"not_available": NotAvailableHere})
    with pytest.raises(NotAvailableHere):
        node(12, _coerce=True)


def test_no_coerce_without_pydantic_plugin_is_a_no_op():
    """_coerce=False and an absent _coerce are honoured with no plugin at all."""

    class PlainService(RoutingClass):
        @route()
        def count(self, number: int) -> int:
            return number

    svc = PlainService()
    assert svc.route.node("count")(12) == 12
    assert svc.route.node("count")(12, _coerce=False) == 12


def test_coerce_never_reaches_the_handler_without_plugin():
    """A **kwargs handler must not see the reserved keyword."""

    class PlainService(RoutingClass):
        @route()
        def echo(self, **kwargs):
            return kwargs

    svc = PlainService()
    assert svc.route.node("echo")(a=1, _coerce=False) == {"a": 1}


def test_coerce_ignored_when_entry_has_no_type_hints():
    """Nothing to convert: _coerce is consumed and the handler runs normally."""
    svc = CoerceService()
    assert svc.route.node("untyped")(a=1, _coerce=True) == {"a": 1}


def test_coerce_ignored_when_validation_is_disabled():
    svc = CoerceService()
    assert svc.route.node("unvalidated")("12", _coerce=True) == "12"


def test_field_strict_false_accepts_string_without_coerce():
    """A per-field Field(strict=False) overrides the model-level strict flag."""
    svc = CoerceService()
    assert svc.route.node("lax_number")("12") == 12


def test_strict_float_accepts_int():
    """Pydantic's strict mode still promotes int to float."""
    svc = CoerceService()
    assert svc.route.node("ratio")(3) == 3.0
