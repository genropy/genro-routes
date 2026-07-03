from __future__ import annotations
import os
import inspect
import importlib.util
from genro_routes import Router, RoutingClass, Section

class MagicClassRouter(RoutingClass):
    """Maps all public methods of a class as routes."""
    def __init__(self, cls: type):
        self._cls = cls

        # We need an instance to bind methods, or we treat them as static
        # For a "repo explorer", we might just map the signatures
        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue
            attr = getattr(cls, attr_name)
            if inspect.isfunction(attr) or inspect.ismethod(attr):
                self.route.add_entry(attr, name=attr_name)

class PythonModuleService(RoutingClass):
    """Exposes internal functions and classes of a Python module as routes."""
    def __init__(self, name: str, file_path: str):
        self.route.plug("pydantic")
        self.file_path = os.path.abspath(file_path)
        self._module_name = name
        self._module = self._import_file(name, file_path)

        if self._module:
            self._map_contents()

    def _import_file(self, name: str, path: str):
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
        except Exception:
            return None
        return None

    def _map_contents(self):
        """Introspects the module and adds its contents as entries."""
        for attr_name in dir(self._module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(self._module, attr_name)

            if inspect.isfunction(attr):
                # Check if function is defined in this file
                try:
                    attr_file = inspect.getsourcefile(attr)
                    if attr_file and os.path.samefile(os.path.abspath(attr_file), self.file_path):
                        self.route.add_entry(attr, name=attr_name)
                except (TypeError, ValueError, OSError):
                    pass
            elif inspect.isclass(attr):
                # Check if class belongs to this module via __module__
                if getattr(attr, "__module__", None) == self._module_name:
                    self.route.include(MagicClassRouter(attr).route, name=attr_name)

class CodeInspector(RoutingClass):
    """Orchestrates the discovery of Python modules as functional routers."""
    def __init__(self, root_path: str):
        self.root = os.path.abspath(root_path)
        self.route.description = "Repository inspector"
        self._discover_modules(self.route, self.root, depth=1)

    def _discover_modules(self, parent_router: Router, current_path: str, depth: int):
        if depth < 0:
            return

        try:
            items = os.listdir(current_path)
        except PermissionError:
            return

        for item in items:
            if item.startswith('.') or item == "__pycache__":
                continue
            full_path = os.path.join(current_path, item)

            if os.path.isdir(full_path):
                section = Section()
                parent_router.include(section.route, name=item)
                self._discover_modules(section.route, full_path, depth - 1)

            elif item.endswith('.py'):
                module_service = PythonModuleService(item[:-3], full_path)
                parent_router.include(module_service.route, name=item[:-3])

if __name__ == "__main__":
    # Explore the mcp_bridge example folder
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_bridge")
    inspector = CodeInspector(target)

    print(f"--- Deep Repo Explorer (Enhanced) ---")

    # Introspect result
    info = inspector.route.nodes()
    routers = info.get("routers", {})

    print(f"Discovered items in bridge folder: {list(routers.keys())}")

    # Check bridge.py (containing classes)
    if "bridge" in routers:
        content = routers["bridge"]
        print(f"\nContents of 'bridge.py':")
        # Now we should see classes as child routers
        classes = content.get("routers", {})
        print(f" - Classes discovered: {list(classes.keys())}")

        if "GenroMCPBridge" in classes:
            methods = list(classes["GenroMCPBridge"].get("entries", {}).keys())
            print(f" - Methods in GenroMCPBridge: {methods}")

    print("\n--- Summary ---")
    print("Fixed: Using os.path.samefile() for robust path comparison.")
    print("Fixed: Now introspecting Classes as sub-routers.")
    print("Fixed: LLM/MCP can now see every class and method in the repository.")
