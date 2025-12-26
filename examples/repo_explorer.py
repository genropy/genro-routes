from __future__ import annotations
import os
from typing import List, Dict, Any
from genro_routes import Router, RoutingClass, route

class RepositoryService(RoutingClass):
    """
    Exposes a repository as a Service.
    
    Instead of mapping every file to a Router (anti-pattern), 
    we provide methods that take paths as arguments.
    """
    
    def __init__(self, root_path: str):
        self.root = os.path.abspath(root_path)
        # Use Pydantic for path validation
        self.api = Router(self, name="repo").plug("pydantic")

    @route("repo")
    def list_dir(self, path: str = ".") -> List[str]:
        """Lists files and directories in a given path."""
        target = self._secure_path(path)
        return os.listdir(target)

    @route("repo")
    def read_file(self, path: str) -> str:
        """Reads the content of a file."""
        target = self._secure_path(path)
        if not os.path.isfile(target):
            raise ValueError(f"Path is not a file: {path}")
        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    @route("repo")
    def get_info(self, path: str) -> Dict[str, Any]:
        """Returns metadata for a file or directory."""
        target = self._secure_path(path)
        stats = os.stat(target)
        return {
            "name": os.path.basename(path),
            "size": stats.st_size,
            "is_dir": os.path.isdir(target),
            "mtime": stats.st_mtime
        }

    def _secure_path(self, path: str) -> str:
        """Ensures the path stays within the root directory."""
        full_path = os.path.abspath(os.path.join(self.root, path))
        if not full_path.startswith(self.root):
            raise PermissionError("Access outside root directory is denied")
        return full_path

if __name__ == "__main__":
    # Explore the current genro-routes repo
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    service = RepositoryService(repo_root)

    print(f"--- Repository Service Demo: {repo_root} ---")
    
    # List root
    print(f"\n1. Listing root:")
    print(service.api.node("list_dir")(path="."))

    # Read README.md
    print(f"\n2. Reading README.md (first 100 chars):")
    try:
        content = service.api.node("read_file")(path="README.md")
        print(content[:100] + "...")
    except Exception as e:
        print(f"Error: {e}")

    # Inspect a folder
    print(f"\n3. Info for 'src':")
    print(service.api.node("get_info")(path="src"))
