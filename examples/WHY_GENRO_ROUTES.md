# Why wrap a library with Genro-Routes?

A common question arises when looking at these examples: *"Why wrap a library like Pygments or Faker if I can just call it directly in my code?"*

The utility of `genro-routes` emerges when you look at the **system architecture**, not just a single script. Here is why wrapping a library as a service makes sense:

## 1. Universal Interface (Network vs. Local)
*   **Pure Library**: You must call it from Python. If you have a JavaScript frontend, a mobile app, or a service in Go, you cannot use it directly.
*   **With Genro-Routes**: The library becomes an endpoint (e.g., `api/highlighter/html`). Any part of your ecosystem can send data and receive results via a standard call, without needing Python installed or knowing the library's internals.

## 2. "Free" Validation (Pydantic)
*   **Pure Library**: If you pass `linenos="string"` instead of a boolean, the library might crash or behave unpredictably. You have to write your own `if isinstance(...)` checks and error handlers.
*   **With Genro-Routes**: The **Pydantic** plugin intercepts errors at the gate. Your handler isn't even executed if the parameters aren't perfect. This makes your service "crash-proof" for all consumers.

## 3. Security and Control (Auth & Env)
*   **Pure Library**: You have no built-in way to track who is using it or to restrict access.
*   **With Genro-Routes**: You can add the **Auth** plugin in seconds. Want to limit expensive operations (like generating huge QR codes) to `admin` users? Just add `auth_tags="admin"` to the method. You gain professional-grade access control without polluting your business logic.

## 4. Automatic Documentation (OpenAPI)
*   **Pure Library**: To know what the library does, developers must read its source code or external documentation.
*   **With Genro-Routes**: Calling `service.api.nodes(mode="openapi")` instantly generates technical documentation (Swagger/OpenAPI). Your colleagues will know exactly which methods are available and what parameters they require without ever seeing your Python code.

## 5. Technical Decoupling (The Contract)
If you decide to switch the underlying implementation (e.g., swapping `Pygments` for a faster Rust-based highlighter), you only change the internal code of your handler. For everyone else in the organization, the endpoint `api/highlighter/html` remains identical. **You have created a stable contract, not just a function call.**

## 6. Automated Documentation at Scale (The "Magic" Pattern)
The "Magic Mapping" technique (dynamic registration) transforms `genro-routes` into a powerful **Documentation Engine**:
*   **Discovery**: It turns an opaque Python object into a transparent, navigable tree.
*   **Standardization**: Every method, docstring, and signature is harvested and translated into standardized formats like **OpenAPI**.
*   **Live Exploration**: It enables the creation of interactive playgrounds (like Swagger UI) for any library without writing a single line of manual documentation code.
*   **Bridge to Non-Python Devs**: It allows developers who don't know Python to explore and understand the capabilities of a Python library through a standard API interface.

## 7. LLM Context and MCP Integration (The AI Bridge)
This is perhaps the most futuristic use case: using `genro-routes` as a bridge for **Model Context Protocol (MCP)**.
*   **Structured Context**: LLMs need structured context to understand what they can "do" with a library. `genro-routes` provides this structure through `nodes()`.
*   **Tool Definition**: An MCP server could use `genro-routes` to automatically generate tool definitions for an LLM. Every route becomes a tool.
*   **Safe Execution**: The built-in Pydantic validation ensures that the LLM sends correctly typed arguments, preventing common "hallucination" errors in function calling.
*   **Discovery**: An LLM can "explore" a large library by navigating the router hierarchy, discovering only the tools relevant to the current task.

---

**Summary**: Use a pure library when writing a local script. Use **Genro-Routes + Library** when you want to offer that functionality as a **reliable, secure, and documented infrastructure asset** to your entire team.
