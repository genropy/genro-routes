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

"""Tests for branch aliases: a virtual branch that is a symlink to another branch.

An alias branch has spec ``{"name": ..., "alias": "<absolute path>"}``. Navigating
into it rewrites the path to the target (resolved from the tree root) and
continues there. Plugins are the target's — the alias is a transparent symlink.
"""

import pytest

from genro_routes import RoutingClass, route

BUILD_LOG: list[str] = []


class Leaf(RoutingClass):
    """A leaf service."""

    def __init__(self, tag: str = "leaf"):
        self.tag = tag
        BUILD_LOG.append(f"Leaf:{tag}")

    @route()
    def ping(self):
        return f"leaf.ping:{self.tag}"

    @route()
    def info(self, x: int):
        return f"leaf.info:{self.tag}:{x}"


class Sub(RoutingClass):
    """A branch that itself has a nested branch (for fractal tests)."""

    def __init__(self):
        BUILD_LOG.append("Sub")
        self.add_branches({"name": "leaf", "cls": Leaf, "params": {"tag": "nested"}})

    @route()
    def top(self):
        return "sub.top"


@pytest.fixture(autouse=True)
def _clear_build_log():
    BUILD_LOG.clear()
    yield
    BUILD_LOG.clear()


# ---------------------------------------------------------------------------
# 1. Basic alias to a real branch
# ---------------------------------------------------------------------------


def test_alias_to_real_branch():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Leaf, "params": {"tag": "r"}},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("fake/ping")() == "leaf.ping:r"
    # Same target reachable under both names.
    assert alfa.route.node("real/ping")() == "leaf.ping:r"


# ---------------------------------------------------------------------------
# 2. Alias exposes the whole subtree (fractal)
# ---------------------------------------------------------------------------


def test_alias_exposes_whole_subtree():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Sub},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("fake/top")() == "sub.top"
    # Nested branch under the target, reached through the alias.
    assert alfa.route.node("fake/leaf/ping")() == "leaf.ping:nested"


# ---------------------------------------------------------------------------
# 3. Alias + lazy target: navigating the alias materializes the target
# ---------------------------------------------------------------------------


def test_alias_to_lazy_target_materializes_on_navigation():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "lazy": True, "cls": Leaf, "params": {"tag": "lz"}},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    assert "Leaf:lz" not in BUILD_LOG  # nothing built at declaration
    assert alfa.route.node("fake/ping")() == "leaf.ping:lz"
    assert "Leaf:lz" in BUILD_LOG  # navigating the alias materialized the target


# ---------------------------------------------------------------------------
# 4. Plugins are the target's (transparent symlink)
# ---------------------------------------------------------------------------


def test_alias_uses_target_plugins():
    class Target(RoutingClass):
        def __init__(self):
            self.route.plug("logging")

        @route()
        def act(self):
            return "act"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Target},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    # Reached via the alias, the node is the target's node with the target's plugin.
    node = alfa.route.node("fake/act")
    assert node() == "act"
    # Same node object as reaching it directly.
    assert alfa.route.node("real/act")() == "act"


# ---------------------------------------------------------------------------
# 5-6. nodes() shows the alias as an UNRESOLVED marker (closed symlink);
#      _eager=True expands everything; basepath opens one branch explicitly
# ---------------------------------------------------------------------------


def test_nodes_shows_alias_as_marker():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Leaf, "params": {"tag": "r"}},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    tree = alfa.route.nodes()
    fake = tree["routers"]["fake"]
    assert fake == {"name": "fake", "alias": "real"}  # marker only, not expanded


def test_nodes_alias_to_lazy_target_does_not_build(  # regression: B1 crash
):
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "lazy": True, "cls": Leaf, "params": {"tag": "lz"}},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    tree = alfa.route.nodes()  # must not crash, must not build
    assert tree["routers"]["fake"] == {"name": "fake", "alias": "real"}
    assert "Leaf:lz" not in BUILD_LOG
    tree_lazy = alfa.route.nodes(lazy=True)  # same in lazy introspection mode
    assert tree_lazy["routers"]["fake"] == {"name": "fake", "alias": "real"}
    assert "Leaf:lz" not in BUILD_LOG


def test_nodes_eager_expands_lazy_and_alias():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "lazy": True, "cls": Leaf, "params": {"tag": "lz"}},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    tree = alfa.route.nodes(_eager=True)
    # Lazy branch materialized and fully expanded.
    assert set(tree["routers"]["real"]["entries"].keys()) == {"ping", "info"}
    # Alias resolved and expanded, keeping the marker.
    fake = tree["routers"]["fake"]
    assert fake["alias"] == "real"
    assert set(fake["entries"].keys()) == {"ping", "info"}
    assert "Leaf:lz" in BUILD_LOG


def test_nodes_eager_expands_nested_lazy():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "sub", "lazy": True, "cls": Sub})

    alfa = Alfa()
    tree = alfa.route.nodes(_eager=True)
    # Nested lazy branch inside the materialized subtree is expanded too.
    assert set(tree["routers"]["sub"]["routers"]["leaf"]["entries"].keys()) == {"ping", "info"}


def test_nodes_eager_alias_cycle_raises():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "a", "alias": "b"},
                    {"name": "b", "alias": "a"},
                ]
            )

    alfa = Alfa()
    with pytest.raises(ValueError, match="cycle"):
        alfa.route.nodes(_eager=True)


def test_nodes_with_alias_cycle_markers_only_no_crash():  # regression: B2
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "a", "alias": "b"},
                    {"name": "b", "alias": "a"},
                ]
            )

    alfa = Alfa()
    tree = alfa.route.nodes()  # markers only: no resolution, no RecursionError
    assert tree["routers"]["a"] == {"name": "a", "alias": "b"}
    assert tree["routers"]["b"] == {"name": "b", "alias": "a"}


def test_router_at_path_alias_cycle_raises():  # regression: B2
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "a", "alias": "b"},
                    {"name": "b", "alias": "a"},
                ]
            )

    alfa = Alfa()
    with pytest.raises(ValueError, match="cycle"):
        alfa.route.router_at_path("a")


def test_nodes_basepath_into_alias():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Leaf, "params": {"tag": "r"}},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    sub = alfa.route.nodes(basepath="fake")
    assert set(sub["entries"].keys()) == {"ping", "info"}


# ---------------------------------------------------------------------------
# 7-8. Deep path and trailing path
# ---------------------------------------------------------------------------


def test_alias_to_deep_path():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Sub},
                    {"name": "fake", "alias": "real/leaf"},  # deep target
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("fake/ping")() == "leaf.ping:nested"


def test_alias_with_trailing_path():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": Sub},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    # fake/leaf/info/... -> real/leaf/info
    assert alfa.route.node("fake/leaf/info")(9) == "leaf.info:nested:9"


# ---------------------------------------------------------------------------
# 9. Broken alias (rotten symlink)
# ---------------------------------------------------------------------------


def test_broken_alias_not_found():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "fake", "alias": "does/not/exist"})

    alfa = Alfa()
    assert alfa.route.node("fake/ping").error == "not_found"


# ---------------------------------------------------------------------------
# 10. Alias cycle
# ---------------------------------------------------------------------------


def test_alias_cycle_raises():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "a", "alias": "b"},
                    {"name": "b", "alias": "a"},
                ]
            )

    alfa = Alfa()
    with pytest.raises(ValueError, match="cycle"):
        alfa.route.node("a/ping")()


# ---------------------------------------------------------------------------
# 11. alias + cls both present -> error
# ---------------------------------------------------------------------------


def test_alias_and_cls_both_present_raises():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "x", "alias": "real", "cls": Leaf})

    with pytest.raises(ValueError, match="alias"):
        Alfa()


# ---------------------------------------------------------------------------
# 12. Alias resolves from the ROOT (absolute), not the declaring router
# ---------------------------------------------------------------------------


def test_alias_resolves_from_root():
    # Alias declared deep in the tree points to an absolute path from the root.
    class Deep(RoutingClass):
        def __init__(self):
            # 'shortcut' points to 'target' which lives at the ROOT, not under Deep
            self.add_branches({"name": "shortcut", "alias": "target"})

    class Root(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "target", "cls": Leaf, "params": {"tag": "root"}},
                    {"name": "deep", "cls": Deep},
                ]
            )

    root = Root()
    assert root.route.node("deep/shortcut/ping")() == "leaf.ping:root"


# ---------------------------------------------------------------------------
# 13. @endpoint_id unchanged: found in eager aliased target
# ---------------------------------------------------------------------------


def test_endpoint_id_still_works_with_alias_present():
    class WithId(RoutingClass):
        @route(endpoint_id="the-ep")
        def act(self):
            return "found"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "real", "cls": WithId},
                    {"name": "fake", "alias": "real"},
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("@the-ep")() == "found"


# ---------------------------------------------------------------------------
# 14. Name collision
# ---------------------------------------------------------------------------


def test_alias_name_collision_raises():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "real", "cls": Leaf})

    alfa = Alfa()
    with pytest.raises(ValueError, match="collision"):
        alfa.add_branches({"name": "real", "alias": "other"})
