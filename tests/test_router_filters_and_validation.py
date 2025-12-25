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

"""Coverage for Router plugin filtering."""

from __future__ import annotations

import pytest

from genro_routes import RoutingClass, Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class _FilterPlugin(BasePlugin):
    plugin_code = "filtertest"
    plugin_description = "Filter test plugin"

    def __init__(self, router, **config):
        super().__init__(router, **config)
        self.calls: list[dict] = []

    def allow_node(self, node, **filters):
        self.calls.append(filters)
        # Hide when custom filter is present, otherwise keep entry visible.
        return not filters.get("hide", False)


class _BadMetadataPlugin(BasePlugin):
    plugin_code = "badmetadata"
    plugin_description = "Bad metadata test plugin"

    def __init__(self, router, **config):
        super().__init__(router, **config)

    def entry_metadata(self, router, entry):
        return ["not-a-dict"]


class _GoodMetadataPlugin(BasePlugin):
    plugin_code = "goodmetadata"
    plugin_description = "Good metadata test plugin"

    def __init__(self, router, **config):
        super().__init__(router, **config)

    def entry_metadata(self, router, entry):
        return {"extra": {"via": self.name}}


def _make_router():
    class Owner(RoutingClass):
        pass

    return Router(Owner(), name="api")


def test_nodes_entry_extra_rejects_non_dict_from_plugin():
    Router.register_plugin(_BadMetadataPlugin)
    router = _make_router().plug("badmetadata")
    entry = MethodEntry("demo", lambda: None, router, plugins=[])

    with pytest.raises(TypeError):
        router._describe_entry_extra(entry, {})


