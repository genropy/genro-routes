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


def test_allow_entry_respects_plugins():
    Router.register_plugin(_FilterPlugin)
    router = _make_router().plug("filtertest")
    entry = MethodEntry("demo", lambda: None, router, plugins=[])

    # hide filter triggers plugin veto (plugin receives extracted filter value without prefix)
    # filters come with plugin_code prefix, e.g., filtertest_hide=True -> {"hide": True}
    assert router._allow_entry(entry, filtertest_hide=True) is False

    # Plugin is ALWAYS consulted, even without kwargs (needed for auth 401/403 logic)
    # With empty kwargs, _FilterPlugin returns True by default
    assert router._allow_entry(entry) is True

    plugin = router._plugins_by_name["filtertest"]
    # 2 calls: plugin is always consulted
    assert len(plugin.calls) == 2
    assert plugin.calls[0] == {"hide": True}
    assert plugin.calls[1] == {}  # empty kwargs on second call


def test_nodes_entry_extra_rejects_non_dict_from_plugin():
    Router.register_plugin(_BadMetadataPlugin)
    router = _make_router().plug("badmetadata")
    entry = MethodEntry("demo", lambda: None, router, plugins=[])

    with pytest.raises(TypeError):
        router._describe_entry_extra(entry, {})


def test_nodes_respects_plugin_allow_skip():
    Router.register_plugin(_FilterPlugin)
    router = _make_router().plug("filtertest")
    router._add_entry(lambda: "ok", name="hidden")

    # Filter is passed with plugin_code prefix; plugin receives extracted value
    # e.g., filtertest_hide=True -> plugin receives {"hide": True}
    tree = router.nodes(filtertest_hide=True)
    assert tree == {}
