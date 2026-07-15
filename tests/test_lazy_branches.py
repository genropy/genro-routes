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

"""Tests for lazy/eager branches: declarative, factory-based subrouters.

A branch is a child subrouter declared as a factory spec
``{"name", "lazy", "cls", "params"}`` and materialized (constructed) only when
needed. Eager branches materialize at first tree access; lazy branches
materialize on-demand at first traversal.
"""

import pytest

from genro_routes import RoutingClass, route

# ---------------------------------------------------------------------------
# Test doubles: leaf classes that record their own construction
# ---------------------------------------------------------------------------

BUILD_LOG: list[str] = []


class Beta(RoutingClass):
    """Beta service (lazy-friendly leaf)."""

    def __init__(self, tag: str = "beta"):
        self.tag = tag
        BUILD_LOG.append(f"Beta:{tag}")

    @route()
    def ping(self):
        return f"beta.ping:{self.tag}"

    @route()
    def info(self, x: int):
        return f"beta.info:{self.tag}:{x}"


class Gamma(RoutingClass):
    """Gamma service."""

    def __init__(self, tag: str = "gamma"):
        self.tag = tag
        BUILD_LOG.append(f"Gamma:{tag}")

    @route()
    def ping(self):
        return f"gamma.ping:{self.tag}"


class Boom(RoutingClass):
    """A leaf whose constructor raises — used for deferred-error tests."""

    def __init__(self):
        BUILD_LOG.append("Boom")
        raise RuntimeError("boom in __init__")

    @route()
    def ping(self):  # pragma: no cover - never reached
        return "never"


@pytest.fixture(autouse=True)
def _clear_build_log():
    BUILD_LOG.clear()
    yield
    BUILD_LOG.clear()


# ---------------------------------------------------------------------------
# add_branches: single dict, list, generator
# ---------------------------------------------------------------------------


def test_add_branches_single_dict():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": False, "cls": Beta, "params": {}})

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"


def test_add_branches_list():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "lazy": False, "cls": Beta, "params": {"tag": "b1"}},
                    {"name": "gamma", "lazy": False, "cls": Gamma, "params": {}},
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:b1"
    assert alfa.route.node("gamma/ping")() == "gamma.ping:gamma"


def test_add_branches_generator():
    def gen():
        yield {"name": "beta", "lazy": True, "cls": Beta, "params": {}}
        yield {"name": "gamma", "lazy": True, "cls": Gamma, "params": {}}

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(gen())

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"
    assert alfa.route.node("gamma/ping")() == "gamma.ping:gamma"


def test_params_applied_to_constructor():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {"tag": "custom"}})

    alfa = Alfa()
    assert alfa.route.node("beta/info")(7) == "beta.info:custom:7"


# ---------------------------------------------------------------------------
# Lazy vs eager timing
# ---------------------------------------------------------------------------


def test_lazy_branch_not_built_until_traversed():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    # Touching the tree must NOT build a lazy branch.
    alfa.route.nodes()
    assert "Beta:beta" not in BUILD_LOG
    # First traversal builds it.
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"
    assert "Beta:beta" in BUILD_LOG


def test_eager_branch_built_at_first_tree_access():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "lazy": False, "cls": Gamma, "params": {}})

    alfa = Alfa()
    assert BUILD_LOG == []  # declaration does not build
    alfa.route.nodes()  # first tree access materializes eager branches
    assert "Gamma:gamma" in BUILD_LOG


def test_declaration_builds_nothing():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "lazy": True, "cls": Beta, "params": {}},
                    {"name": "gamma", "lazy": False, "cls": Gamma, "params": {}},
                ]
            )

    Alfa()  # __init__ only declares
    assert BUILD_LOG == []


def test_mixed_lazy_and_eager_same_list():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "lazy": True, "cls": Beta, "params": {}},
                    {"name": "gamma", "lazy": False, "cls": Gamma, "params": {}},
                ]
            )

    alfa = Alfa()
    alfa.route.nodes()  # eager gamma built, lazy beta not
    assert "Gamma:gamma" in BUILD_LOG
    assert "Beta:beta" not in BUILD_LOG
    alfa.route.node("beta/ping")()  # now beta builds
    assert "Beta:beta" in BUILD_LOG


def test_lazy_built_only_once():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.route.node("beta/ping")()
    alfa.route.node("beta/info")(1)
    alfa.route.node("beta/ping")()
    assert BUILD_LOG.count("Beta:beta") == 1


def test_eager_guard_idempotent():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "lazy": False, "cls": Gamma, "params": {}})

    alfa = Alfa()
    alfa.route.nodes()
    alfa.route.nodes()
    alfa.route.node("gamma/ping")()
    assert BUILD_LOG.count("Gamma:gamma") == 1


# ---------------------------------------------------------------------------
# Introspection: nodes() describes lazy branches without building them
# ---------------------------------------------------------------------------


def test_nodes_lists_lazy_branch_without_building():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    assert "beta" in tree["routers"]
    assert "Beta:beta" not in BUILD_LOG


def test_nodes_marks_branch_as_lazy():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    beta_node = tree["routers"]["beta"]
    assert beta_node.get("lazy") is True


def test_nodes_shows_class_declared_leaves_without_building():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    beta_node = tree["routers"]["beta"]
    # Leaves read from the class @route markers, no instance built.
    assert set(beta_node["entries"].keys()) == {"ping", "info"}
    assert "Beta:beta" not in BUILD_LOG


def test_nodes_eager_branch_is_fully_expanded():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "lazy": False, "cls": Gamma, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    assert "gamma" in tree["routers"]
    assert set(tree["routers"]["gamma"]["entries"].keys()) == {"ping"}


# ---------------------------------------------------------------------------
# Reverse lookup: node("@id") skips non-materialized lazy branches
# ---------------------------------------------------------------------------


def test_endpoint_id_skips_lazy_branch():
    class WithId(RoutingClass):
        @route(endpoint_id="hidden-ep")
        def action(self):
            return "hidden"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "lazy": True, "cls": WithId, "params": {}})

    alfa = Alfa()
    node = alfa.route.node("@hidden-ep")
    assert node.error == "not_found"  # lazy branch not searched


def test_endpoint_id_found_after_materialization():
    class WithId(RoutingClass):
        @route(endpoint_id="visible-ep")
        def action(self):
            return "visible"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "lazy": True, "cls": WithId, "params": {}})

    alfa = Alfa()
    alfa.route.node("child/action")()  # materialize
    node = alfa.route.node("@visible-ep")
    assert node.error is None
    assert node() == "visible"


def test_endpoint_id_found_in_eager_branch():
    class WithId(RoutingClass):
        @route(endpoint_id="eager-ep")
        def action(self):
            return "eager"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "lazy": False, "cls": WithId, "params": {}})

    alfa = Alfa()
    assert alfa.route.node("@eager-ep")() == "eager"


# ---------------------------------------------------------------------------
# Materialization wires parent chain, ctx and plugins
# ---------------------------------------------------------------------------


def test_materialized_branch_has_routing_parent():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    child_router = alfa.route.node("beta/ping")._router
    assert child_router.instance._routing_parent is alfa


def test_plugin_inherited_on_materialization():
    class Alfa(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    child_router = alfa.route.node("beta/ping")._router
    assert "logging" in child_router._plugins_by_name


def test_plug_after_declare_reaches_lazy_branch():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})
            self.route.plug("logging")  # plugged after declaration

    alfa = Alfa()
    child_router = alfa.route.node("beta/ping")._router
    assert "logging" in child_router._plugins_by_name


# ---------------------------------------------------------------------------
# Deferred construction errors
# ---------------------------------------------------------------------------


def test_lazy_constructor_error_deferred_to_traversal():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "boom", "lazy": True, "cls": Boom, "params": {}})

    alfa = Alfa()  # no error at declaration
    assert "Boom" not in BUILD_LOG
    with pytest.raises(RuntimeError, match="boom in __init__"):
        alfa.route.node("boom/ping")()


# ---------------------------------------------------------------------------
# branches property (read view) and remove_branch
# ---------------------------------------------------------------------------


def test_branches_property_lists_declared_specs():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "lazy": True, "cls": Beta, "params": {}},
                    {"name": "gamma", "lazy": False, "cls": Gamma, "params": {}},
                ]
            )

    alfa = Alfa()
    assert set(alfa.branches) == {"beta", "gamma"}


def test_remove_branch_before_materialization():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.remove_branch("beta")
    assert "beta" not in alfa.branches
    node = alfa.route.node("beta/ping")
    assert node.error == "not_found"
    assert "Beta:beta" not in BUILD_LOG


def test_remove_branch_after_materialization_detaches():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.route.node("beta/ping")()  # materialize
    alfa.remove_branch("beta")
    node = alfa.route.node("beta/ping")
    assert node.error == "not_found"


def test_add_branch_runtime_after_init():
    class Alfa(RoutingClass):
        pass

    alfa = Alfa()
    alfa.add_branches({"name": "beta", "lazy": True, "cls": Beta, "params": {}})
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"


# ---------------------------------------------------------------------------
# Nesting: a lazy branch that itself declares lazy branches
# ---------------------------------------------------------------------------


def test_nested_lazy_branches_expand_incrementally():
    class Inner(RoutingClass):
        def __init__(self):
            BUILD_LOG.append("Inner")

        @route()
        def leaf(self):
            return "inner.leaf"

    class Mid(RoutingClass):
        def __init__(self):
            BUILD_LOG.append("Mid")
            self.add_branches({"name": "inner", "lazy": True, "cls": Inner, "params": {}})

        @route()
        def midleaf(self):
            return "mid.midleaf"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "mid", "lazy": True, "cls": Mid, "params": {}})

    alfa = Alfa()
    assert BUILD_LOG == []
    # Reach mid: builds Mid, not Inner.
    assert alfa.route.node("mid/midleaf")() == "mid.midleaf"
    assert "Mid" in BUILD_LOG
    assert "Inner" not in BUILD_LOG
    # Reach inner: now Inner builds.
    assert alfa.route.node("mid/inner/leaf")() == "inner.leaf"
    assert "Inner" in BUILD_LOG
