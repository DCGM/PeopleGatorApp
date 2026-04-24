---
description: "Use when implementing HTTP APIs or service endpoints in Python. Enforces typed FastAPI endpoints and Pydantic models for request and response schemas."
name: "Typed FastAPI And Pydantic"
applyTo: "**/*.py"
---
# Typed FastAPI And Pydantic

- For new Python APIs, use FastAPI.
- Use Pydantic models for request and response bodies.
- Keep endpoints fully typed, including path and query parameters, request models, and response models.
- Prefer explicit response_model declarations for route handlers.
- Use dependency injection with typed dependencies.
- Use absolute package imports in API code; avoid relative imports.
- Keep API validation and schema logic in Pydantic models, not ad hoc dictionaries.

## Do Not

- Do not return raw `dict` from route handlers — always use a Pydantic `response_model`.
- Do not perform blocking I/O in route handlers — use `async` and asyncio-compatible clients.
- Do not put business logic inside route handlers — delegate to service functions or repositories.
- Do not access `request.body()` for JSON — define a Pydantic body model instead.
- Do not skip `status_code` declarations on mutation endpoints (POST/PUT/DELETE).
