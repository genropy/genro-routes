# Copyright 2025-2026 Softwell S.r.l.
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


"""RoutingContext - Extensible execution context with parent chain delegation.

Provides a simple, extensible context object for routing. Each adapter (ASGI,
Telegram, CLI, etc.) creates a ``RoutingContext`` and attaches whatever
attributes it needs (``db``, ``session``, ``avatar``, etc.).

Missing attribute lookups walk up the ``_parent`` chain via ``__getattr__``,
so child contexts inherit from parent contexts automatically.

Example::

    from genro_routes import RoutingContext

    # Server boot
    server_ctx = RoutingContext()
    server_ctx.server = server

    # App mount
    app_ctx = RoutingContext(parent=server_ctx)
    app_ctx.app = app

    # Per-request
    ctx = RoutingContext(parent=app_ctx)
    ctx.request = request
    ctx.db = request.db
    ctx.session = request.session

    # Handler reads ctx.db (local), ctx.server (walks up parent chain)
"""

from __future__ import annotations

__all__ = ["RoutingContext"]


class RoutingContext:
    """Extensible execution context with parent chain delegation.

    No slots, no ABC. Free ``__dict__`` for the adapter to attach any
    attribute. Missing attributes walk up ``_parent`` chain via
    ``__getattr__``.
    """

    def __init__(self, parent: RoutingContext | None = None):
        self._parent = parent

    def __getattr__(self, name: str):
        try:
            parent = object.__getattribute__(self, "_parent")
        except AttributeError:
            raise AttributeError(name) from None
        if parent is not None:
            return getattr(parent, name)
        raise AttributeError(name)
