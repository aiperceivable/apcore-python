<div align="center">
  <img src="https://raw.githubusercontent.com/aipartnerup/apcore-typescript/main/apcore-logo.svg" alt="apcore logo" width="200"/>
</div>

# apcore

Schema-driven module development framework for AI-perceivable interfaces.

**apcore** provides a unified task orchestration framework with strict type safety, access control, middleware pipelines, and built-in observability. It enables you to define modules with structured input/output schemas that are easily consumed by LLMs and other automated systems.

## Features

- **Schema-driven modules** -- Define input/output contracts using Pydantic models with automatic validation
- **10-step execution pipeline** -- Context creation, safety checks, ACL enforcement, validation, middleware chains, and execution with timeout support
- **`@module` decorator** -- Turn plain functions into fully schema-aware modules with zero boilerplate
- **YAML bindings** -- Register modules declaratively without modifying source code
- **Access control (ACL)** -- Pattern-based, first-match-wins rules with wildcard support
- **Middleware system** -- Composable before/after hooks with error recovery
- **Observability** -- Tracing (spans), metrics collection, and structured context logging
- **Async support** -- Seamless sync and async module execution
- **Safety guards** -- Call depth limits, circular call detection, frequency throttling
- **Approval system** -- Pluggable approval gate (Step 4.5) with sync/async handlers, Phase B resume, and audit events
- **Extension points** -- Unified extension management for discoverers, middleware, ACL, approval handlers, span exporters, and module validators
- **Async task management** -- Background module execution with status tracking, cancellation, and concurrency limiting
- **W3C Trace Context** -- traceparent header injection/extraction for distributed tracing interop

## Requirements

- Python >= 3.11

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

### Define a module with the decorator

```python
from apcore import module

@module(description="Add two integers", tags=["math"])
def add(a: int, b: int) -> int:
    return a + b
```

### Define a module with a class

```python
from pydantic import BaseModel
from apcore import Context

class GreetInput(BaseModel):
    name: str

class GreetOutput(BaseModel):
    message: str

class GreetModule:
    input_schema = GreetInput
    output_schema = GreetOutput
    description = "Greet a user"

    def execute(self, inputs: dict, context: Context) -> dict:
        return {"message": f"Hello, {inputs['name']}!"}
```

### Register and execute

```python
from apcore import Registry, Executor

registry = Registry()
registry.register("greet", GreetModule())

executor = Executor(registry=registry)
result = executor.call("greet", {"name": "Alice"})
# {"message": "Hello, Alice!"}
```

### Add middleware

```python
from apcore import LoggingMiddleware, TracingMiddleware

executor.use(LoggingMiddleware())
executor.use(TracingMiddleware())
```

### Access control

```python
from apcore import ACL, ACLRule

acl = ACL(rules=[
    ACLRule(callers=["admin.*"], targets=["*"], effect="allow", description="Admins can call anything"),
    ACLRule(callers=["*"], targets=["admin.*"], effect="deny", description="Others cannot call admin modules"),
])
executor = Executor(registry=registry, acl=acl)
```

## Project Structure

```
src/apcore/
    __init__.py          # Public API
    async_task.py        # Background task manager
    cancel.py            # Cooperative cancellation primitives
    context.py           # Execution context & identity
    executor.py          # Core execution engine
    decorator.py         # @module decorator
    bindings.py          # YAML binding loader
    config.py            # Configuration
    acl.py               # Access control
    approval.py          # Approval system
    extensions.py        # Extension point manager
    errors.py            # Error hierarchy
    module.py            # Module annotations & metadata
    trace_context.py     # W3C trace context helpers
    middleware/          # Middleware system
    observability/       # Tracing, metrics, logging
    registry/            # Module discovery & registration
    schema/              # Schema loading, validation, export
    utils/               # Utilities
```

## Development

### Run tests

```bash
pytest
```

### Run tests with coverage

```bash
pytest --cov=src/apcore --cov-report=html
```

### Lint and format

```bash
ruff check --fix src/ tests/
ruff format src/ tests/
```

### Type check

```bash
mypy src/ tests/
```


## 📄 License

Apache-2.0

## 🔗 Links

- **Documentation**: [docs/apcore](https://github.com/aipartnerup/apcore) - Complete documentation
- **Website**: [aipartnerup.com](https://aipartnerup.com)
- **GitHub**: [aipartnerup/apcore-python](https://github.com/aipartnerup/apcore-python)
- **PyPI**: [apcore](https://pypi.org/project/apcore/)
- **Issues**: [GitHub Issues](https://github.com/aipartnerup/apcore-python/issues)
- **Discussions**: [GitHub Discussions](https://github.com/aipartnerup/apcore-python/discussions)
