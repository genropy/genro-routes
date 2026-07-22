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

"""Tests for declarative branches: factory (lazy) and instance (eager) subrouters.

A branch is a child subrouter declared through ``add_branches``. Each spec is one
of three mutually exclusive forms:

- factory ``{"name", "cls", "params"}`` — always **lazy**: the instance is
  constructed on the first traversal of the branch (e.g. ``node("beta/ping")``),
  never at tree access. ``nodes()`` describes the branch from the class alone,
  without building it.
- instance ``{"name", "instance"}`` — **eager**: an already-built instance,
  linked as a child immediately (it enters ``_children`` at once and never
  appears in ``branches``). ``params`` is not allowed with ``instance``.
- alias ``{"name", "alias"}`` — a symlink to an absolute path.

There is no ``lazy`` flag: the timing is derived from the form.
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
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"


def test_add_branches_list():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "cls": Beta, "params": {"tag": "b1"}},
                    {"name": "gamma", "cls": Gamma, "params": {}},
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:b1"
    assert alfa.route.node("gamma/ping")() == "gamma.ping:gamma"


def test_add_branches_generator():
    def gen():
        yield {"name": "beta", "cls": Beta, "params": {}}
        yield {"name": "gamma", "cls": Gamma, "params": {}}

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(gen())

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"
    assert alfa.route.node("gamma/ping")() == "gamma.ping:gamma"


def test_params_applied_to_constructor():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {"tag": "custom"}})

    alfa = Alfa()
    assert alfa.route.node("beta/info")(7) == "beta.info:custom:7"


# ---------------------------------------------------------------------------
# Lazy vs eager timing
# ---------------------------------------------------------------------------


def test_lazy_branch_not_built_until_traversed():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    # Touching the tree must NOT build a lazy branch.
    alfa.route.nodes()
    assert "Beta:beta" not in BUILD_LOG
    # First traversal builds it.
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"
    assert "Beta:beta" in BUILD_LOG


def test_instance_branch_built_immediately():
    # An instance branch is EAGER: the instance is built by the caller and
    # linked at once. Since Gamma logs its own construction, the log records
    # the build before add_branches even runs.
    gamma = Gamma()
    assert "Gamma:gamma" in BUILD_LOG

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "instance": gamma})

    alfa = Alfa()
    # No further build happens; the branch is already a live child.
    assert BUILD_LOG.count("Gamma:gamma") == 1
    assert alfa.route.node("gamma/ping")() == "gamma.ping:gamma"


def test_declaration_builds_nothing():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "cls": Beta, "params": {}},
                    {"name": "gamma", "cls": Gamma, "params": {}},
                ]
            )

    Alfa()  # __init__ only declares factory branches
    assert BUILD_LOG == []


def test_mixed_lazy_factory_and_eager_instance_same_list():
    # An eager instance (built by the caller) and a lazy factory in the same
    # list: the instance is already in the log; the factory is not built until
    # traversed.
    gamma = Gamma()
    assert BUILD_LOG == ["Gamma:gamma"]

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "beta", "cls": Beta, "params": {}},  # lazy factory
                    {"name": "gamma", "instance": gamma},  # eager instance
                ]
            )

    alfa = Alfa()
    # Declaration does not build the lazy factory; the instance was already built.
    assert "Beta:beta" not in BUILD_LOG
    assert BUILD_LOG.count("Gamma:gamma") == 1
    alfa.route.node("beta/ping")()  # now the factory builds
    assert "Beta:beta" in BUILD_LOG


def test_lazy_built_only_once():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.route.node("beta/ping")()
    alfa.route.node("beta/info")(1)
    alfa.route.node("beta/ping")()
    assert BUILD_LOG.count("Beta:beta") == 1


def test_instance_branch_never_rebuilt():
    # An instance branch is built once by the caller; repeated tree access and
    # traversal never re-run the constructor.
    gamma = Gamma()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "instance": gamma})

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
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    assert "beta" in tree["routers"]
    assert "Beta:beta" not in BUILD_LOG


def test_nodes_marks_branch_as_lazy():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    beta_node = tree["routers"]["beta"]
    assert beta_node.get("lazy") is True


def test_nodes_shows_class_declared_leaves_without_building():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    beta_node = tree["routers"]["beta"]
    # Leaves read from the class @route markers, no instance built.
    assert set(beta_node["entries"].keys()) == {"ping", "info"}
    assert "Beta:beta" not in BUILD_LOG


def test_nodes_instance_branch_is_fully_expanded():
    # An instance branch is already a live child, so nodes() expands it fully
    # (not as a lazy marker).
    gamma = Gamma()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "instance": gamma})

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
            self.add_branches({"name": "child", "cls": WithId, "params": {}})

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
            self.add_branches({"name": "child", "cls": WithId, "params": {}})

    alfa = Alfa()
    alfa.route.node("child/action")()  # materialize
    node = alfa.route.node("@visible-ep")
    assert node.error is None
    assert node() == "visible"


def test_endpoint_id_found_in_instance_branch():
    # An instance branch is a live child, so its endpoint_id is reachable at
    # once (no traversal needed). Lazy factory branches, by contrast, stay
    # hidden from @id lookup until traversed (see test_endpoint_id_skips_lazy_branch).
    class WithId(RoutingClass):
        @route(endpoint_id="eager-ep")
        def action(self):
            return "eager"

    child = WithId()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "instance": child})

    alfa = Alfa()
    assert alfa.route.node("@eager-ep")() == "eager"


# ---------------------------------------------------------------------------
# Materialization wires parent chain, ctx and plugins
# ---------------------------------------------------------------------------


def test_materialized_branch_has_routing_parent():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    child_router = alfa.route.node("beta/ping")._router
    assert child_router.instance._routing_parent is alfa


def test_plugin_inherited_on_materialization():
    class Alfa(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    child_router = alfa.route.node("beta/ping")._router
    assert "logging" in child_router._plugins_by_name


def test_plug_after_declare_reaches_lazy_branch():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})
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
            self.add_branches({"name": "boom", "cls": Boom, "params": {}})

    alfa = Alfa()  # no error at declaration
    assert "Boom" not in BUILD_LOG
    with pytest.raises(RuntimeError, match="boom in __init__"):
        alfa.route.node("boom/ping")()
    # The failing spec is NOT lost: the branch stays declared and the error
    # is repeatable on the next traversal (no silent disappearance).
    assert "boom" in alfa.branches
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
                    {"name": "beta", "cls": Beta, "params": {}},
                    {"name": "gamma", "cls": Gamma, "params": {}},
                ]
            )

    alfa = Alfa()
    assert set(alfa.branches) == {"beta", "gamma"}


def test_remove_branch_before_materialization():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.remove_branch("beta")
    assert "beta" not in alfa.branches
    node = alfa.route.node("beta/ping")
    assert node.error == "not_found"
    assert "Beta:beta" not in BUILD_LOG


def test_remove_branch_after_materialization_detaches():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.route.node("beta/ping")()  # materialize
    alfa.remove_branch("beta")
    node = alfa.route.node("beta/ping")
    assert node.error == "not_found"


def test_add_branch_runtime_after_init():
    class Alfa(RoutingClass):
        pass

    alfa = Alfa()
    alfa.add_branches({"name": "beta", "cls": Beta, "params": {}})
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
            self.add_branches({"name": "inner", "cls": Inner, "params": {}})

        @route()
        def midleaf(self):
            return "mid.midleaf"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "mid", "cls": Mid, "params": {}})

    alfa = Alfa()
    assert BUILD_LOG == []
    # Reach mid: builds Mid, not Inner.
    assert alfa.route.node("mid/midleaf")() == "mid.midleaf"
    assert "Mid" in BUILD_LOG
    assert "Inner" not in BUILD_LOG
    # Reach inner: now Inner builds.
    assert alfa.route.node("mid/inner/leaf")() == "inner.leaf"
    assert "Inner" in BUILD_LOG


# ---------------------------------------------------------------------------
# Spec validation and defaults
# ---------------------------------------------------------------------------


def test_branch_name_collision_with_branch_raises():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    with pytest.raises(ValueError, match="collision"):
        alfa.add_branches({"name": "beta", "cls": Gamma, "params": {}})


def test_branch_name_collision_with_materialized_child_raises():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    alfa.route.node("beta/ping")()  # materialize -> beta now in _children
    with pytest.raises(ValueError, match="collision"):
        alfa.add_branches({"name": "beta", "cls": Gamma, "params": {}})


def test_params_defaults_to_empty():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta})  # no params

    alfa = Alfa()
    assert alfa.route.node("beta/ping")() == "beta.ping:beta"


def test_factory_is_always_lazy():
    # A factory spec (``cls``) is always lazy: touching the tree with nodes()
    # never builds it; only a traversal does.
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "gamma", "cls": Gamma, "params": {}})

    alfa = Alfa()
    alfa.route.nodes()  # nodes() never builds a factory
    assert "Gamma:gamma" not in BUILD_LOG
    alfa.route.node("gamma/ping")()  # traversal builds it
    assert "Gamma:gamma" in BUILD_LOG


# ---------------------------------------------------------------------------
# remove_branch edge cases
# ---------------------------------------------------------------------------


def test_remove_nonexistent_branch_is_noop():
    class Alfa(RoutingClass):
        pass

    alfa = Alfa()
    alfa.remove_branch("nope")  # must not raise


def test_branches_property_drops_spec_after_materialization():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    assert "beta" in alfa.branches
    alfa.route.node("beta/ping")()  # materialize
    # Spec leaves _branches once materialized (it's now a real child).
    assert "beta" not in alfa.branches


# ---------------------------------------------------------------------------
# Reaching a branch without a sub-path
# ---------------------------------------------------------------------------


def test_lazy_factory_alone_matches_instance_branch_behavior():
    # A branch reached without a sub-path has no callable entry of its own
    # (no default_entry): a lazy factory and an eager instance resolve the
    # same way.
    eager = Beta()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches(
                [
                    {"name": "lz", "cls": Beta, "params": {}},
                    {"name": "eg", "instance": eager},
                ]
            )

    alfa = Alfa()
    assert alfa.route.node("lz").error == alfa.route.node("eg").error


# ---------------------------------------------------------------------------
# nodes(basepath=...) opens (materializes) a lazy branch
# ---------------------------------------------------------------------------


def test_nodes_basepath_materializes_lazy_branch():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    sub = alfa.route.nodes(basepath="beta")
    assert set(sub["entries"].keys()) == {"ping", "info"}
    assert "Beta:beta" in BUILD_LOG  # opening via basepath built it


def test_nodes_basepath_deep_into_nested_lazy():
    class Inner(RoutingClass):
        @route()
        def leaf(self):
            return "inner.leaf"

    class Mid(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "inner", "cls": Inner, "params": {}})

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "mid", "cls": Mid, "params": {}})

    alfa = Alfa()
    sub = alfa.route.nodes(basepath="mid/inner")
    assert set(sub["entries"].keys()) == {"leaf"}


# ---------------------------------------------------------------------------
# @route(name=...) alias shown in lazy nodes() (class-level scan)
# ---------------------------------------------------------------------------


def test_lazy_nodes_shows_route_name_alias():
    class Aliased(RoutingClass):
        @route(name="public_name")
        def internal_name(self):
            return "x"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "cls": Aliased, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    entries = tree["routers"]["child"]["entries"]
    assert "public_name" in entries
    assert "internal_name" not in entries


# ---------------------------------------------------------------------------
# Interaction with the existing nodes(lazy=True) introspection flag
# ---------------------------------------------------------------------------


def test_nodes_lazy_flag_still_describes_declared_branches():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes(lazy=True)
    assert "beta" in tree["routers"]
    assert "Beta:beta" not in BUILD_LOG


# ---------------------------------------------------------------------------
# Double materialization is defended (idempotent per name)
# ---------------------------------------------------------------------------


def test_materialize_branch_idempotent_direct():
    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "beta", "cls": Beta, "params": {}})

    alfa = Alfa()
    r1 = alfa.route._materialize_branch("beta")
    r2 = alfa.route._materialize_branch("beta")
    assert r1 is r2
    assert BUILD_LOG.count("Beta:beta") == 1


# ---------------------------------------------------------------------------
# Inherited @route leaf is scanned from the class (MRO), no duplicates
# ---------------------------------------------------------------------------


def test_lazy_nodes_scans_inherited_route_leaves():
    class Base(RoutingClass):
        @route()
        def base_leaf(self):
            return "base"

    class Derived(Base):
        @route()
        def own_leaf(self):
            return "own"

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "cls": Derived, "params": {}})

    alfa = Alfa()
    tree = alfa.route.nodes()
    entries = tree["routers"]["child"]["entries"]
    assert set(entries.keys()) == {"base_leaf", "own_leaf"}


def test_lazy_nodes_dedups_same_function_under_two_attrs():
    # Same function object bound to two class attributes must be scanned once.
    class Aliased(RoutingClass):
        @route()
        def real(self):
            return "r"

        alias = real  # second attribute -> same function id

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "cls": Aliased, "params": {}})

    alfa = Alfa()
    entries = alfa.route.nodes()["routers"]["child"]["entries"]
    assert list(entries.keys()) == ["real"]


def test_lazy_nodes_branch_with_no_leaves():
    # A lazy branch whose class declares no @route leaves: described as lazy,
    # with no "entries" key.
    class Empty(RoutingClass):
        """A leaf-less grouping class."""

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "child", "cls": Empty, "params": {}})

    alfa = Alfa()
    child_info = alfa.route.nodes()["routers"]["child"]
    assert child_info["lazy"] is True
    assert "entries" not in child_info


# ---------------------------------------------------------------------------
# Instance form: eager, already-built, validated against cls/params
# ---------------------------------------------------------------------------


def test_instance_form_rejects_params():
    obj = Beta()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "x", "instance": obj, "params": {}})

    with pytest.raises(ValueError, match="params"):
        Alfa()


def test_instance_and_cls_mutually_exclusive():
    obj = Beta()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "x", "instance": obj, "cls": Beta})

    with pytest.raises(ValueError, match="exactly one"):
        Alfa()


def test_instance_already_bound_rejected():
    obj = Beta()

    class ParentA(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "x", "instance": obj})

    ParentA()  # obj is now bound to a ParentA instance

    class ParentB(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "x", "instance": obj})

    with pytest.raises(ValueError, match="already bound"):
        ParentB()


def test_instance_not_in_branches_view():
    obj = Beta()

    class Alfa(RoutingClass):
        def __init__(self):
            self.add_branches({"name": "x", "instance": obj})

    alfa = Alfa()
    # An instance branch is a live child, not a declared spec: it never appears
    # in the branches view, but nodes() lists it among the child routers.
    assert "x" not in alfa.branches
    assert "x" in alfa.route.nodes()["routers"]
