from __future__ import annotations
from genro_routes import Router, RoutingClass, route
from genro_routes.exceptions import NotAuthenticated, NotAuthorized

class SecureService(RoutingClass):
    def __init__(self):
        # We plug the 'auth' plugin to enable role-based access control
        self.api = Router(self, name="api").plug("auth")

    @route("api")
    def public_info(self):
        """Available to everyone."""
        return {"status": "online", "access": "public"}

    # This node requires 'user' tag
    @route("api", auth_tags="user")
    def user_profile(self):
        """Requires a valid user role."""
        return {"profile": "User Data", "access": "restricted"}

    # This node requires 'admin' tag
    @route("api", auth_tags="admin")
    def admin_settings(self):
        """Requires administrative privileges."""
        return {"settings": "System Config", "access": "admin_only"}

if __name__ == "__main__":
    service = SecureService()

    print("--- 1. Public Access ---")
    node = service.api.node("public_info")
    print(f"Result: {node()}")

    print("\n--- 2. Accessing User Data WITHOUT roles ---")
    try:
        # Calling without providing auth_tags in kwargs
        service.api.node("user_profile")()
    except NotAuthenticated:
        print("Caught expected: NotAuthenticated (401)")

    print("\n--- 3. Accessing User Data WITH 'user' role ---")
    # We pass current user capabilities to the node resolution
    user_node = service.api.node("user_profile", auth_tags="user")
    print(f"Result: {user_node()}")

    print("\n--- 4. Accessing Admin Data WITH 'user' role ---")
    try:
        # Providing 'user' tag for an 'admin' required node
        service.api.node("admin_settings", auth_tags="user")()
    except NotAuthorized:
        print("Caught expected: NotAuthorized (403)")

    print("\n--- 5. Accessing Admin Data WITH 'admin' role ---")
    admin_node = service.api.node("admin_settings", auth_tags="admin")
    print(f"Result: {admin_node()}")
