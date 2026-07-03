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

"""Tests for the logging plugin."""

# Import to trigger plugin registration
import genro_routes.plugins.logging  # noqa: F401
from genro_routes import RoutingClass, route


class LoggedService(RoutingClass):
    def __init__(self):
        self.calls = 0
        self.route.plug("logging")

    @route()
    def hello(self):
        self.calls += 1
        return "ok"


def test_logging_plugin_runs_per_instance(monkeypatch):
    records = []

    class DummyLogger:
        def __init__(self):
            self._handlers = True

        def has_handlers(self):
            return True

        # Compatibility alias
        hasHandlers = has_handlers  # noqa: N815

        def info(self, message):
            records.append(message)

    svc = LoggedService()
    svc.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

    assert svc.route.node("hello")() == "ok"
    assert svc.calls == 1
    assert records and "hello" in records[0]

    other = LoggedService()
    assert other.calls == 0


def test_logging_plugin_respects_route_plugin_flags():
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            # Inject dummy logger so we can see if logging fires.
            self.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route(logging_flags="enabled:off")
        def hello(self):
            return "hi"

    svc = Service()
    svc.route.node("hello")()
    assert records == []


def test_logging_plugin_respects_runtime_config_toggle():
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route()
        def ping(self):
            return "pong"

    svc = Service()
    # Disable "before" and keep "after" via flags.
    svc.route.logging.configure(flags="before:off,after:on")
    svc.route.node("ping")()
    # Check format: "ping end (X.XX ms)" - timing varies so we check pattern
    assert len(records) == 1
    assert records[0].startswith("ping end (") and records[0].endswith(" ms)")


def test_logging_plugin_print_sink_overrides_logger(capsys):
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route(logging_log=False, logging_print=True)
        def hello(self):
            return "hi"

    svc = Service()
    svc.route.node("hello")()
    # Should bypass logger and print instead.
    captured = capsys.readouterr()
    assert records == []
    assert "hello start" in captured.out and "hello end" in captured.out


def test_configure_enabled_false_disables_plugin():
    """Test that configure(enabled=False) actually disables the plugin (issue #8)."""
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route()
        def hello(self):
            return "hi"

    svc = Service()

    # First call - logging should fire
    svc.route.node("hello")()
    assert len(records) == 2  # start + end

    # Disable via configure
    svc.route.logging.configure(enabled=False)

    # Second call - logging should be disabled
    records.clear()
    svc.route.node("hello")()
    assert records == []  # No logging because plugin is disabled


def test_configure_enabled_per_handler():
    """Test that configure(_target=handler, enabled=False) disables only that handler."""
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route()
        def hello(self):
            return "hi"

        @route()
        def world(self):
            return "world"

    svc = Service()

    # Disable only 'hello' via configure
    svc.route.logging.configure(_target="hello", enabled=False)

    # Call hello - should NOT log
    svc.route.node("hello")()
    assert records == []

    # Call world - SHOULD log
    svc.route.node("world")()
    assert len(records) == 2  # start + end


def test_set_plugin_enabled_overrides_configure():
    """Test that set_plugin_enabled (locals) overrides configure (config)."""
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutingClass):
        def __init__(self):
            self.route.plug("logging")
            self.route.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route()
        def hello(self):
            return "hi"

    svc = Service()

    # Disable via configure (config)
    svc.route.logging.configure(enabled=False)

    # But re-enable via set_plugin_enabled (locals) - should take precedence
    svc.route.set_plugin_enabled("hello", "logging", True)

    svc.route.node("hello")()
    assert len(records) == 2  # Logging fires because locals override config
