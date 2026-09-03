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

"""CLI transport adapter for genro-routes.

Usage::

    from genro_routes.cli import RoutingCli
    from myapp import MyService

    cli = RoutingCli(MyService)
    cli.run()
"""

from typing import Any

import click

from genro_routes.core.routing import RoutingClass

from ._builder import CliBuilder

__all__ = ["RoutingCli"]


class RoutingCli:
    """CLI transport adapter for RoutingClass.

    Accepts a RoutingClass subclass or an instance. If a class is passed
    it is instantiated without arguments.
    """

    def __init__(
        self,
        target: type | RoutingClass,
        *,
        name: str | None = None,
        output_format: str = "auto",
    ) -> None:
        if isinstance(target, type):
            self._instance = target()
        else:
            self._instance = target

        builder = CliBuilder(self._instance, output_format=output_format)
        self._click_group = builder.build(name=name)

    @property
    def click_group(self) -> click.Group:
        """The generated click command tree (useful for testing or embedding)."""
        return self._click_group

    def run(self, args: list[str] | None = None, standalone_mode: bool = True) -> Any:
        """Launch the CLI."""
        return self._click_group(args=args, standalone_mode=standalone_mode)
