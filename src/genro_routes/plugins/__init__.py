"""Plugin package for Genro Routes.

This package contains built-in plugins for the Router.

Note: Do not import concrete plugins here to keep imports side-effect free.
Concrete plugin modules (logging, pydantic) self-register when imported
via the main genro_routes package.
"""

__all__: list[str] = []
