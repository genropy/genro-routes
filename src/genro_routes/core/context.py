# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""RoutingContext - Abstract execution context for routing.

This module provides the abstract base class for execution contexts. Each adapter
(ASGI, Telegram, CLI, etc.) provides its own concrete implementation.

Example::

    from genro_routes import RoutingContext

    class ASGIContext(RoutingContext):
        def __init__(self, request, app, server):
            self._request = request
            self._app = app
            self._server = server

        @property
        def db(self):
            return self._request.state.db

        @property
        def avatar(self):
            return self._request.state.avatar

        @property
        def session(self):
            return self._request.state.session

        @property
        def app(self):
            return self._app

        @property
        def server(self):
            return self._server
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["RoutingContext"]


class RoutingContext(ABC):
    """Abstract execution context for routing.

    Subclass this to provide adapter-specific context (ASGI, Telegram, CLI, etc.).
    The concrete implementation is responsible for managing sync/async concerns
    (e.g., using ContextVar for async environments).

    Properties:
        db: Database connection or session.
        avatar: Current user identity with metadata (permissions, locale, etc.).
        session: Session (macro context) for user state.
        app: Application instance.
        server: Server instance.
    """

    @property
    @abstractmethod
    def db(self) -> Any:
        """Database connection or session."""
        ...

    @property
    @abstractmethod
    def avatar(self) -> Any:
        """Current user identity with metadata (permissions, locale, etc.)."""
        ...

    @property
    @abstractmethod
    def session(self) -> Any:
        """Session (macro context) for user state."""
        ...

    @property
    @abstractmethod
    def app(self) -> Any:
        """Application instance."""
        ...

    @property
    @abstractmethod
    def server(self) -> Any:
        """Server instance."""
        ...
