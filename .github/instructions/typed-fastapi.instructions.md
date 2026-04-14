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
- Keep API validation and schema logic in Pydantic models, not ad hoc dictionaries.
