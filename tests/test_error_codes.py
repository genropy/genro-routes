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

"""Contract tests for the three outcomes of a RouterNode call (issue #50).

A call to a node ends in exactly one of three ways:

1. the arguments do not fit the handler signature -> ``signature_error``,
   raised before the handler runs (default class: TypeError);
2. the signature is satisfied and pydantic rejects the values ->
   ``validation_error`` (default class: pydantic's ValidationError);
3. the handler body raises -> that exception propagates untouched, TypeError
   included, with no error code and no wrapping.
"""

import asyncio

import pytest

# Import to trigger plugin registration
import genro_routes.plugins.pydantic  # noqa: F401
from genro_routes import RoutingClass, route


class SignatureError(Exception):
    """Custom class mapped to 'signature_error' by the tests below."""

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(selector)


class ValidationFailure(Exception):
    """Custom class mapped to 'validation_error' by the tests below."""

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(selector)


BOTH_CODES = {
    "signature_error": SignatureError,
    "validation_error": ValidationFailure,
}


class TypedService(RoutingClass):
    """Handlers with type hints, validated by the pydantic plugin."""

    def __init__(self):
        self.route.plug("pydantic")

    @route()
    def concat(self, text: str, number: int = 1) -> str:
        return f"{text}:{number}"

    @route()
    def count(self, number: int) -> int:
        return number

    @route()
    def get_user(self, user_id) -> str:
        return f"user={user_id}"

    @route()
    def broken_type(self, text: str) -> str:
        raise TypeError(f"body failure for {text}")

    @route()
    def broken_value(self, text: str) -> str:
        raise ValueError(f"body failure for {text}")


class PlainService(RoutingClass):
    """Same handlers without the pydantic plugin."""

    @route()
    def concat(self, text, number=1):
        return f"{text}:{number}"

    @route()
    def count(self, number):
        return number


class AsyncService(RoutingClass):
    @route()
    async def broken_type(self, text):
        raise TypeError(f"body failure for {text}")

    @route()
    async def echo(self, text):
        return text


# ----------------------------------------------------------------------
# 1. Arguments that do not fit the signature -> signature_error
# ----------------------------------------------------------------------


def test_unknown_keyword_maps_to_signature_error_with_pydantic():
    node = TypedService().route.node("concat", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        node("a", nope=1)


def test_unknown_keyword_maps_to_signature_error_without_pydantic():
    node = PlainService().route.node("concat", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        node("a", nope=1)


def test_unknown_keyword_is_plain_typeerror_when_unmapped():
    with pytest.raises(TypeError):
        TypedService().route.node("concat")("a", nope=1)
    with pytest.raises(TypeError):
        PlainService().route.node("concat")("a", nope=1)


def test_missing_required_argument_maps_to_signature_error():
    node = TypedService().route.node("count", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        node()
    plain = PlainService().route.node("count", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        plain()


def test_missing_required_argument_is_plain_typeerror_when_unmapped():
    with pytest.raises(TypeError):
        TypedService().route.node("count")()
    with pytest.raises(TypeError):
        PlainService().route.node("count")()


def test_too_many_positionals_maps_to_signature_error():
    node = TypedService().route.node("concat", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        node("a", 1, "extra")


def test_signature_error_selector_carries_router_and_path():
    node = TypedService().route.node("concat", errors=BOTH_CODES)
    with pytest.raises(SignatureError) as excinfo:
        node("a", nope=1)
    assert excinfo.value.selector.endswith(":concat")


def test_coerce_with_bad_keyword_maps_to_signature_error():
    """_coerce is reserved: it is excluded from the bind, the bad keyword is not."""
    node = TypedService().route.node("count", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        node(number=1, nope=2, _coerce=True)


def test_coerce_alone_still_reaches_the_handler():
    node = TypedService().route.node("count")
    assert node(number="12", _coerce=True) == 12


# ----------------------------------------------------------------------
# 2. Signature satisfied, values rejected by pydantic -> validation_error
# ----------------------------------------------------------------------


def test_pydantic_refusal_maps_to_validation_error_not_signature_error():
    node = TypedService().route.node("count", errors=BOTH_CODES)
    with pytest.raises(ValidationFailure):
        node("12")  # strict by default: a str is not an int


def test_pydantic_refusal_on_keyword_maps_to_validation_error():
    node = TypedService().route.node("concat", errors=BOTH_CODES)
    with pytest.raises(ValidationFailure):
        node(text="a", number="12")


# ----------------------------------------------------------------------
# 3. Handler body -> propagates untouched
# ----------------------------------------------------------------------


def test_body_typeerror_propagates_even_when_both_codes_are_mapped():
    node = TypedService().route.node("broken_type", errors=BOTH_CODES)
    with pytest.raises(TypeError, match="body failure for a"):
        node("a")


def test_body_valueerror_propagates_untouched():
    node = TypedService().route.node("broken_value", errors=BOTH_CODES)
    with pytest.raises(ValueError, match="body failure for a"):
        node("a")


def test_async_body_typeerror_surfaces_at_await_not_at_call():
    node = AsyncService().route.node("broken_type", errors=BOTH_CODES)
    coro = node("a")  # the call itself must not raise

    async def run():
        await coro

    with pytest.raises(TypeError, match="body failure for a"):
        asyncio.run(run())


def test_async_signature_error_is_raised_at_call_time():
    node = AsyncService().route.node("echo", errors=BOTH_CODES)
    with pytest.raises(SignatureError):
        node("a", nope=1)


# ----------------------------------------------------------------------
# Happy paths and registration
# ----------------------------------------------------------------------


def test_path_segment_fills_the_positional_without_signature_error():
    node = TypedService().route.node("get_user/12", errors=BOTH_CODES)
    assert node() == "user=12"


def test_method_entry_exposes_the_handler_signature():
    """The entry carries the signature the bind uses, cached after first access."""
    entry = TypedService().route._entries["concat"]
    assert list(entry.signature.parameters) == ["text", "number"]
    assert entry.signature is entry.signature
