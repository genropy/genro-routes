from __future__ import annotations
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter, TerminalFormatter
from genro_routes import Router, RoutingClass, route

class HighlightingService(RoutingClass):
    """Wraps the Pygments library to provide syntax highlighting as a service."""
    
    def __init__(self):
        # We use Pydantic for robust input validation of code and options
        self.api = Router(self, name="highlighter").plug("pydantic")

    @route("highlighter")
    def html(self, code: str, language: str = "python", linenos: bool = False) -> str:
        """Generates HTML highlighted code."""
        lexer = get_lexer_by_name(language)
        formatter = HtmlFormatter(linenos=linenos)
        return highlight(code, lexer, formatter)

    @route("highlighter")
    def terminal(self, code: str, language: str = "python") -> str:
        """Generates ANSI terminal highlighted code."""
        lexer = get_lexer_by_name(language)
        formatter = TerminalFormatter()
        return highlight(code, lexer, formatter)

if __name__ == "__main__":
    service = HighlightingService()
    
    sample_code = "def hello(): print('Hello Genro!')"

    print("--- 1. Terminal Highlighting ---")
    # Resolution via paths
    node = service.api.node("terminal")
    print(node(code=sample_code, language="python"))

    print("\n--- 2. HTML Highlighting ---")
    html_node = service.api.node("html")
    html_output = html_node(code=sample_code, language="python", linenos=True)
    print(f"Generated HTML (first 50 chars): {html_output[:50]}...")

    print("\n--- 3. Pydantic Validation in action ---")
    try:
        # Pydantic will complain if 'linenos' is not a boolean
        service.api.node("html")(code=sample_code, linenos="not-a-boolean")
    except Exception as e:
        print(f"Caught expected validation error: {e}")
