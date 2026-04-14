---
description: "Use when implementing or refactoring Python code. Enforces modern Python 3.12+ typing style, inline generics, and typed-first implementation patterns."
name: "Modern Python Implementation"
applyTo: "**/*.py"
---
# Modern Python Implementation

- Target Python 3.12+ language features and typing syntax.
- Use modern built-in generic syntax (for example list[str], dict[str, int], tuple[int, ...]).
- Use inline type parameters and generic syntax available in modern Python (PEP 695 style) where applicable.
- Use explicit, precise type hints for public functions, methods, class attributes, and return values.
- Use dataclasses, TypedDict, Protocol, and Literal where they improve type safety and readability.
- Do not introduce untyped public APIs.
