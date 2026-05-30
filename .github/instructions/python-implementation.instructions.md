---
description: "Use when implementing or refactoring Python code. Enforces modern Python 3.12+ typing style, inline generics, and typed-first implementation patterns."
name: "Modern Python Implementation"
applyTo: "**/*.py"
---
# Modern Python Implementation

## Strict typing — non-negotiable requirement

Strict, complete typing is **mandatory** for every piece of code in this codebase — not just public APIs. This applies to all functions, methods, class attributes, variables, closures, lambdas, and internal helpers without exception.

**Do not skip or defer type annotations under any circumstances.** If you find yourself unable to annotate something correctly, choose a narrower type, introduce a `TypedDict`, `Protocol`, or `dataclass`, or refactor — do not fall back to `Any` or untyped signatures.

### Prohibited — never use these without explicit written justification

- `Any` — forbidden unless interfacing with a third-party library that has no stubs and there is genuinely no alternative; must be accompanied by an inline comment explaining why no specific type is possible.
- `cast()` — forbidden as a shortcut to silence type errors; only permitted when the type checker cannot narrow a type that is provably correct at runtime, with an inline comment explaining the invariant.
- `object` as a stand-in type — use a specific base class, `Protocol`, or generic instead.
- Untyped parameters or return values (e.g. `def foo(x, y)` with no annotations).
- `# type: ignore` without a specific error code and an explanatory comment on the same line.

### Required patterns

- Target Python 3.12+ language features and typing syntax.
- Use modern built-in generic syntax (`list[str]`, `dict[str, int]`, `tuple[int, ...]`).
- Use inline type parameters (PEP 695) for generic classes and functions where applicable.
- Annotate **every** function parameter, return type, and class attribute — public and private alike.
- Use `TypedDict` for typed dict shapes, `Protocol` for structural interfaces, `Literal` for fixed value sets, and `dataclass` / `NamedTuple` for structured data.
- Use `| None` instead of `Optional[T]` and `X | Y` instead of `Union[X, Y]`.
- Do not import `List`, `Dict`, `Tuple`, `Set`, `Optional`, or `Union` from `typing` — use built-in generics and `|` syntax instead.
- Prefer absolute package imports (`from people_gator_api.db.models import ...`) over relative imports.
- Do not use relative imports (`from .foo` or `from ..bar`).
