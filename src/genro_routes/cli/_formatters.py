# Copyright 2025 Softwell S.r.l. — Apache License 2.0
"""Output formatters for CLI handler results."""

import json
from typing import Any

from genro_routes.core.routing import is_result_wrapper


class OutputFormatter:
    """Formats handler return values for terminal display."""

    def __init__(self, output_format: str = "auto"):
        self._format = output_format

    def format(self, value: Any) -> str | None:
        """Format a value for terminal output. Returns None for no output."""
        if is_result_wrapper(value):
            value = value.value

        if value is None:
            return None

        formatter = getattr(self, f"_format_{self._format}", self._format_auto)
        return formatter(value)

    def _format_auto(self, value: Any) -> str:
        """Auto-detect best format."""
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, default=str, ensure_ascii=False)
        return str(value)

    def _format_json(self, value: Any) -> str:
        """Always JSON."""
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)

    def _format_table(self, value: Any) -> str:
        """Table format if rich is available, otherwise JSON fallback."""
        if isinstance(value, list) and value and isinstance(value[0], dict):
            try:
                return self._rich_table(value)
            except ImportError:
                pass
        return self._format_json(value)

    def _format_raw(self, value: Any) -> str:
        """Raw repr."""
        return repr(value)

    def _rich_table(self, rows: list[dict]) -> str:
        """Render list-of-dicts as a rich table."""
        from io import StringIO

        from rich.console import Console
        from rich.table import Table

        columns = list(rows[0].keys())
        table = Table(*columns)
        for row in rows:
            table.add_row(*(str(row.get(c, "")) for c in columns))

        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        console.print(table)
        return buf.getvalue()
