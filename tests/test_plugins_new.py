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
from genro_routes import RoutedClass, Router, route


class LoggedService(RoutedClass):
    def __init__(self):
        self.calls = 0
        self.routes = Router(self, name="routes").plug("logging")

    @route("routes")
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
    svc.routes.logging._logger = DummyLogger()  # type: ignore[attr-defined]

    assert svc.routes.get("hello")() == "ok"
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

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            # Inject dummy logger so we can see if logging fires.
            self.api.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route("api", logging_flags="enabled:off")
        def hello(self):
            return "hi"

    svc = Service()
    svc.api.get("hello")()
    assert records == []


def test_logging_plugin_respects_runtime_config_toggle():
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.api.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route("api")
        def ping(self):
            return "pong"

    svc = Service()
    # Disable "before" and keep "after" via flags.
    svc.api.logging.configure(flags="before:off,after:on")
    svc.api.get("ping")()
    assert records and records == ["ping end (0.00 ms)"]


def test_logging_plugin_print_sink_overrides_logger(capsys):
    records = []

    class DummyLogger:
        def has_handlers(self):
            return True

        def info(self, message):
            records.append(message)

    class Service(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")
            self.api.logging._logger = DummyLogger()  # type: ignore[attr-defined]

        @route("api", logging_log=False, logging_print=True)
        def hello(self):
            return "hi"

    svc = Service()
    svc.api.get("hello")()
    # Should bypass logger and print instead.
    captured = capsys.readouterr()
    assert records == []
    assert "hello start" in captured.out and "hello end" in captured.out
