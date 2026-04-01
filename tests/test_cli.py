# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for CLI transport adapter."""

import json
from enum import Enum
from typing import Literal, Optional

import pytest
from click.testing import CliRunner

from genro_routes import Router, RoutingClass, route
from genro_routes.cli import RoutingCli


# ---------------------------------------------------------------------------
# Test fixtures: RoutingClass examples
# ---------------------------------------------------------------------------

class SimpleService(RoutingClass):
    """A simple test service."""

    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def hello(self, name: str = "world"):
        return f"Hello {name}"

    @route("api")
    def add(self, a: int, b: int):
        """Add two numbers."""
        return a + b

    @route("api")
    def greet(self, name: str):
        """Greet someone by name."""
        return f"Hi {name}!"


class MultiRouterService(RoutingClass):
    """Service with multiple routers."""

    def __init__(self):
        self.api = Router(self, name="api")
        self.admin = Router(self, name="admin")

    @route("api")
    def status(self):
        return {"status": "ok"}

    @route("admin")
    def reset(self):
        return "reset done"


class TypedService(RoutingClass):
    """Service with various parameter types."""

    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def with_flag(self, verbose: bool = False):
        return f"verbose={verbose}"

    @route("api")
    def with_optional(self, name: Optional[str] = None):
        return f"name={name}"

    @route("api")
    def with_literal(self, mode: Literal["fast", "slow"] = "fast"):
        return f"mode={mode}"

    @route("api")
    def with_list(self, items: list[str] = ()):
        return f"items={list(items)}"


class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class EnumService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def paint(self, color: Color = Color.RED):
        return f"color={color.name}"


class ChildService(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def detail(self, item_id: int):
        return f"item={item_id}"


class ParentService(RoutingClass):
    """Service with child hierarchy."""

    def __init__(self):
        self.api = Router(self, name="api")
        self.child = ChildService()
        self.api.attach_instance(self.child, name="items")

    @route("api")
    def index(self):
        return "parent index"


# ---------------------------------------------------------------------------
# Tests: RoutingCli instantiation
# ---------------------------------------------------------------------------

class TestRoutingCliInit:

    def test_accepts_class(self):
        cli = RoutingCli(SimpleService)
        assert cli.click_group is not None

    def test_accepts_instance(self):
        svc = SimpleService()
        cli = RoutingCli(svc)
        assert cli.click_group is not None

    def test_custom_name(self):
        cli = RoutingCli(SimpleService, name="myapp")
        assert cli.click_group.name == "myapp"

    def test_default_name_from_class(self):
        cli = RoutingCli(SimpleService)
        assert cli.click_group.name == "simpleservice"


# ---------------------------------------------------------------------------
# Tests: command structure
# ---------------------------------------------------------------------------

class TestCommandStructure:

    def test_single_router_commands_at_root(self):
        cli = RoutingCli(SimpleService)
        cmd_names = set(cli.click_group.commands.keys())
        assert "hello" in cmd_names
        assert "add" in cmd_names
        assert "greet" in cmd_names

    def test_multi_router_creates_subgroups(self):
        cli = RoutingCli(MultiRouterService)
        cmd_names = set(cli.click_group.commands.keys())
        assert "api" in cmd_names
        assert "admin" in cmd_names

    def test_multi_router_subgroup_has_commands(self):
        cli = RoutingCli(MultiRouterService)
        api_group = cli.click_group.commands["api"]
        assert "status" in api_group.commands

    def test_child_hierarchy(self):
        cli = RoutingCli(ParentService)
        group = cli.click_group
        assert "index" in group.commands
        assert "items" in group.commands
        items_group = group.commands["items"]
        assert "detail" in items_group.commands


# ---------------------------------------------------------------------------
# Tests: command invocation
# ---------------------------------------------------------------------------

class TestInvocation:

    def setup_method(self):
        self.runner = CliRunner()

    def test_hello_default(self):
        cli = RoutingCli(SimpleService)
        result = self.runner.invoke(cli.click_group, ["hello"])
        assert result.exit_code == 0
        assert "Hello world" in result.output

    def test_hello_with_option(self):
        cli = RoutingCli(SimpleService)
        result = self.runner.invoke(cli.click_group, ["hello", "--name", "Alice"])
        assert result.exit_code == 0
        assert "Hello Alice" in result.output

    def test_positional_argument(self):
        cli = RoutingCli(SimpleService)
        result = self.runner.invoke(cli.click_group, ["greet", "Bob"])
        assert result.exit_code == 0
        assert "Hi Bob!" in result.output

    def test_add_positional_args(self):
        cli = RoutingCli(SimpleService)
        result = self.runner.invoke(cli.click_group, ["add", "3", "4"])
        assert result.exit_code == 0
        assert "7" in result.output

    def test_dict_output_is_json(self):
        cli = RoutingCli(MultiRouterService)
        result = self.runner.invoke(cli.click_group, ["api", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {"status": "ok"}

    def test_multi_router_command(self):
        cli = RoutingCli(MultiRouterService)
        result = self.runner.invoke(cli.click_group, ["admin", "reset"])
        assert result.exit_code == 0
        assert "reset done" in result.output


# ---------------------------------------------------------------------------
# Tests: typed parameters
# ---------------------------------------------------------------------------

class TestTypedParams:

    def setup_method(self):
        self.runner = CliRunner()
        self.cli = RoutingCli(TypedService)

    def test_bool_flag(self):
        result = self.runner.invoke(self.cli.click_group, ["with-flag", "--verbose"])
        assert result.exit_code == 0
        assert "verbose=True" in result.output

    def test_bool_flag_negated(self):
        result = self.runner.invoke(self.cli.click_group, ["with-flag", "--no-verbose"])
        assert result.exit_code == 0
        assert "verbose=False" in result.output

    def test_optional(self):
        result = self.runner.invoke(self.cli.click_group, ["with-optional", "--name", "test"])
        assert result.exit_code == 0
        assert "name=test" in result.output

    def test_optional_default(self):
        result = self.runner.invoke(self.cli.click_group, ["with-optional"])
        assert result.exit_code == 0
        assert "name=None" in result.output

    def test_literal_choice(self):
        result = self.runner.invoke(self.cli.click_group, ["with-literal", "--mode", "slow"])
        assert result.exit_code == 0
        assert "mode=slow" in result.output

    def test_literal_invalid(self):
        result = self.runner.invoke(self.cli.click_group, ["with-literal", "--mode", "turbo"])
        assert result.exit_code != 0

    def test_list_multiple(self):
        result = self.runner.invoke(
            self.cli.click_group, ["with-list", "--items", "a", "--items", "b"]
        )
        assert result.exit_code == 0
        assert "items=['a', 'b']" in result.output


class TestEnumParam:

    def test_enum_choice(self):
        runner = CliRunner()
        cli = RoutingCli(EnumService)
        result = runner.invoke(cli.click_group, ["paint", "--color", "GREEN"])
        assert result.exit_code == 0
        assert "color=GREEN" in result.output

    def test_enum_invalid(self):
        runner = CliRunner()
        cli = RoutingCli(EnumService)
        result = runner.invoke(cli.click_group, ["paint", "--color", "YELLOW"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Tests: help text
# ---------------------------------------------------------------------------

class TestHelp:

    def setup_method(self):
        self.runner = CliRunner()

    def test_root_help(self):
        cli = RoutingCli(SimpleService)
        result = self.runner.invoke(cli.click_group, ["--help"])
        assert result.exit_code == 0
        assert "hello" in result.output
        assert "add" in result.output

    def test_command_help(self):
        cli = RoutingCli(SimpleService)
        result = self.runner.invoke(cli.click_group, ["add", "--help"])
        assert result.exit_code == 0
        assert "Add two numbers" in result.output

    def test_multi_router_help(self):
        cli = RoutingCli(MultiRouterService)
        result = self.runner.invoke(cli.click_group, ["--help"])
        assert result.exit_code == 0
        assert "api" in result.output
        assert "admin" in result.output


# ---------------------------------------------------------------------------
# Tests: child hierarchy invocation
# ---------------------------------------------------------------------------

class TestChildInvocation:

    def test_invoke_child_handler(self):
        runner = CliRunner()
        cli = RoutingCli(ParentService)
        result = runner.invoke(cli.click_group, ["items", "detail", "42"])
        assert result.exit_code == 0
        assert "item=42" in result.output

    def test_invoke_parent_handler(self):
        runner = CliRunner()
        cli = RoutingCli(ParentService)
        result = runner.invoke(cli.click_group, ["index"])
        assert result.exit_code == 0
        assert "parent index" in result.output


# ---------------------------------------------------------------------------
# Tests: output format
# ---------------------------------------------------------------------------

class TestOutputFormat:

    def test_json_format(self):
        runner = CliRunner()
        cli = RoutingCli(MultiRouterService, output_format="json")
        result = runner.invoke(cli.click_group, ["api", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {"status": "ok"}

    def test_raw_format(self):
        runner = CliRunner()
        cli = RoutingCli(MultiRouterService, output_format="raw")
        result = runner.invoke(cli.click_group, ["admin", "reset"])
        assert result.exit_code == 0
        assert "'reset done'" in result.output

    def test_none_return_no_output(self):
        class NoneService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api")
            def noop(self):
                return None

        runner = CliRunner()
        cli = RoutingCli(NoneService)
        result = runner.invoke(cli.click_group, ["noop"])
        assert result.exit_code == 0
        assert result.output.strip() == ""
