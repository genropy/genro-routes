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

"""Core runtime aggregator for Genro Routes.

Exposes the runtime building blocks from a single module:
``BaseRouter``, ``Router``, ``route``, ``RoutingClass``.

Public API:
    - ``BaseRouter``: Plugin-free routing engine
    - ``Router``: Plugin-enabled router with middleware support
    - ``route``: Decorator for marking handler methods
    - ``RoutingClass``: Mixin for classes exposing routers

Importing this module performs only imports; it does not register plugins
or instantiate routers.
"""

from .base_router import BaseRouter
from .context import RoutingContext
from .decorators import route
from .router import Router
from .router_interface import RouterInterface
from .routing import RoutingClass, is_result_wrapper

__all__ = [
    "BaseRouter",
    "Router",
    "RouterInterface",
    "RoutingClass",
    "RoutingContext",
    "is_result_wrapper",
    "route",
]
