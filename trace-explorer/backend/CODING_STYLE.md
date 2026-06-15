# Coding Style

## Toolchain

Three tools run on every change. All must pass with zero errors before merging.

```bash
uv run ruff format .   # format
uv run ruff check .    # lint
uv run ty check .      # type check
```

Install the dev group first if the tools are not present:

```bash
uv sync --group dev
```

## Formatting

`ruff format` is the single source of truth for formatting. It is not configurable per-file. The only project-level setting is:

- **Line length:** 100 characters

Do not run `black` or `autopep8`. Do not manually reformat code that `ruff format` would change.

## Linting

`ruff check` enforces the following rule sets (configured in `pyproject.toml`):

| Code | Rule set | Purpose |
|------|----------|---------|
| `E` / `W` | pycodestyle | PEP 8 errors and warnings |
| `F` | pyflakes | Undefined names, unused imports |
| `I` | isort | Import ordering |
| `B` | flake8-bugbear | Common bug patterns |
| `C4` | flake8-comprehensions | Unnecessary comprehension constructs |
| `UP` | pyupgrade | Modernise syntax for Python 3.12 |
| `A` | flake8-builtins | Catches parameter names that shadow builtins (e.g. `range`, `id`, `type`) |
| `D1` | pydocstyle | Missing docstrings |
| `RUF` | ruff-specific | Additional correctness rules |

To auto-fix everything that can be fixed automatically:

```bash
uv run ruff check --fix .
```

## Type checking

`ty` (Astral's type checker) is used instead of mypy. Target Python version is 3.12.

All functions must have fully annotated parameters and return types. Use built-in generic syntax (`list[str]`, `dict[str, Any]`) rather than `typing.List` / `typing.Dict`. Import `Any` from `typing` only when a looser type is genuinely unavoidable.

```python
# correct
def _span_attrs(span: dict[str, Any]) -> dict[str, Any]: ...

# wrong
from typing import Dict
def _span_attrs(span: Dict) -> Dict: ...
```

Import `AsyncGenerator` from `collections.abc`, not `typing`:

```python
from collections.abc import AsyncGenerator  # correct
from typing import AsyncGenerator            # wrong (UP035)
```

## Docstrings

All functions (public and private) must have docstrings. **Google style** is enforced by ruff (`convention = "google"`).

### One-line docstrings

Use a single line when the purpose is fully captured by the summary:

```python
def _span_attrs(span: dict[str, Any]) -> dict[str, Any]:
    """Return a flat key/value dict for all attributes on an OTLP span."""
```

### Multi-line docstrings

Use `Args:`, `Returns:`, and `Raises:` sections where the function has non-obvious parameters or a non-trivial return value. Do not repeat type information that is already in the signature.

```python
async def _get_trace(client: httpx.AsyncClient, trace_id: str) -> list[dict[str, Any]]:
    """Fetch a single trace by ID, retrying up to 5 times on HTTP 429.

    Args:
        client: Shared async HTTP client.
        trace_id: Hex trace ID to fetch.

    Returns:
        A list of OTLP batch dicts as returned by ``GET /api/traces/{id}``.

    Raises:
        httpx.HTTPStatusError: If Tempo returns a non-2xx response other than
            429, or if all 5 retry attempts are exhausted due to rate limiting.
    """
```

Use `Yields:` instead of `Returns:` for generator / async generator functions:

```python
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """...

    Yields:
        Nothing; control is yielded to FastAPI while the server is running.
    """
```

Use double backticks for inline code references inside docstrings (``like this``).

## Imports

Imports are auto-sorted by `ruff check` (isort rules). The expected order is:

1. Standard library
2. Third-party packages
3. First-party modules (`tempo` is declared as first-party in `pyproject.toml`)

Separate each group with a blank line. Do not use wildcard imports (`from x import *`).

## Naming

- **Never shadow Python builtins.** The `A` rule set enforces this. Common offenders: `range`, `id`, `type`, `input`, `list`, `dict`.
- When a FastAPI query parameter must be named after a reserved word, rename the Python variable and use `alias=` in the `Query(...)` annotation:

```python
# correct: HTTP param is still named "range", Python variable is "time_range"
async def get_sessions(time_range: str = Query("24h", alias="range", ...)):

# wrong: shadows the built-in range()
async def get_sessions(range: str = Query("24h", ...)):
```

## Constants

Magic numbers and repeated string literals must be extracted as module-level constants with `SCREAMING_SNAKE_CASE` names and explicit type annotations:

```python
_TRACE_FETCH_CONCURRENCY: int = 10
_HTTP_TIMEOUT_SECONDS: int = 30
_QUERY_ALL_SESSIONS: str = '{resource.service.name="opencode"} | select(.session.id)'
```

## Error handling and dead code

- Do not leave unreachable statements after a `raise` or unconditional `return`.
- Use `zip(..., strict=True)` whenever two sequences are expected to be the same length. This converts a silent length mismatch into an explicit `ValueError`.
- Retry loops must raise an explicit exception on exhaustion rather than returning a sentinel value.

## HTTP client

A single `httpx.AsyncClient` is created at application startup via the FastAPI `lifespan` context manager and stored in `app.state.http_client`. Route handlers retrieve it from `request.app.state.http_client` and pass it down to service functions. **Do not** create a new `AsyncClient` inside a request handler or service function; doing so discards connection pooling.

## Concurrency

When fetching multiple Tempo traces in parallel, use `_fetch_traces_by_ids` rather than reimplementing the semaphore + `asyncio.gather` pattern inline. The concurrency limit is `_TRACE_FETCH_CONCURRENCY = 25`.

The semaphore is a module-level singleton (`_fetch_semaphore`) shared across all concurrent endpoint calls. Do not create a new `asyncio.Semaphore` inside a function; doing so defeats the global cap and allows simultaneous endpoint requests to collectively exceed the intended limit.

## Caching

Use `_cached_fetch_all_traces` instead of calling `_fetch_all_traces` directly in public endpoint handlers. It provides two guarantees:

1. **TTL caching** — results are reused for `_CACHE_TTL_SECONDS` seconds, so repeated requests (e.g. browser polling) do not hit Tempo every time.
2. **Request coalescing** — concurrent callers with the same key (e.g. `/api/sessions` and `/api/overview` on page load) share one in-flight fetch rather than each issuing their own.

## Tests

Tests live in a `tests/` directory and are discovered by `pytest`. The `asyncio_mode = "auto"` setting in `pyproject.toml` means async test functions do not need the `@pytest.mark.asyncio` decorator.
