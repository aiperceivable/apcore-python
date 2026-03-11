<div align="center">
  <img src="https://raw.githubusercontent.com/aipartnerup/apcore/main/apcore-logo.svg" alt="apcore logo" width="200"/>
</div>

# apcore

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)

Schema-driven module development framework for AI-perceivable interfaces.

**apcore** provides a unified task orchestration framework with strict type safety, access control, middleware pipelines, and built-in observability. It enables you to define modules with structured input/output schemas that are easily consumed by LLMs and other automated systems.

## Features

- **Schema-driven modules** -- Define input/output contracts using Pydantic models with automatic validation
- **11-step execution pipeline** -- Context creation, safety checks, ACL enforcement, approval gate, validation, middleware chains, and execution with timeout support
- **`@module` decorator** -- Turn plain functions into fully schema-aware modules with zero boilerplate
- **YAML bindings** -- Register modules declaratively without modifying source code
- **Access control (ACL)** -- Pattern-based, first-match-wins rules with wildcard support
- **Middleware system** -- Composable before/after hooks with error recovery
- **Observability** -- Tracing (spans), metrics collection, and structured context logging
- **Async support** -- Seamless sync and async module execution
- **Safety guards** -- Call depth limits, circular call detection, frequency throttling
- **Approval system** -- Pluggable approval gate (Step 5) with sync/async handlers, Phase B resume, and audit events
- **Extension points** -- Unified extension management for discoverers, middleware, ACL, approval handlers, span exporters, and module validators
- **Async task management** -- Background module execution with status tracking, cancellation, and concurrency limiting
- **W3C Trace Context** -- traceparent header injection/extraction for distributed tracing interop

## API Overview

**Core**

| Class | Description |
|-------|-------------|
| `APCore` | High-level client -- register modules, call, stream, validate |
| `Registry` | Module storage -- discover, register, get, list, watch |
| `Executor` | Execution engine -- call with middleware pipeline, ACL, approval |
| `Context` | Request context -- trace ID, identity, call chain, cancel token |
| `Config` | Configuration -- load from YAML, get/set values |
| `Identity` | Caller identity -- id, type, roles, attributes |
| `FunctionModule` | Wrapped function module created by `@module` decorator |

**Access Control & Approval**

| Class | Description |
|-------|-------------|
| `ACL` | Access control -- rule-based caller/target authorization |
| `ApprovalHandler` | Pluggable approval gate protocol |
| `AlwaysDenyHandler` / `AutoApproveHandler` / `CallbackApprovalHandler` | Built-in approval handlers |

**Middleware**

| Class | Description |
|-------|-------------|
| `Middleware` | Pipeline hooks -- before/after/on_error interception |
| `BeforeMiddleware` / `AfterMiddleware` | Single-phase middleware adapters |
| `LoggingMiddleware` | Structured logging middleware |
| `RetryMiddleware` | Automatic retry with backoff |
| `ErrorHistoryMiddleware` | Records errors into ErrorHistory |
| `PlatformNotifyMiddleware` | Emits events on error rate/latency spikes |

**Schema**

| Class | Description |
|-------|-------------|
| `SchemaLoader` | Load schemas from YAML or native types |
| `SchemaValidator` | Validate data against schemas |
| `SchemaExporter` | Export schemas for MCP, OpenAI, Anthropic, generic |
| `RefResolver` | Resolve `$ref` references in JSON Schema |

**Observability**

| Class | Description |
|-------|-------------|
| `TracingMiddleware` | Distributed tracing with span export |
| `MetricsMiddleware` / `MetricsCollector` | Call count, latency, error rate metrics |
| `ContextLogger` | Context-aware structured logging |
| `ErrorHistory` | Ring buffer of recent errors with deduplication |
| `UsageCollector` | Per-module usage statistics and trends |

**Events & Extensions**

| Class | Description |
|-------|-------------|
| `EventEmitter` | Event system -- subscribe, emit, flush |
| `WebhookSubscriber` / `A2ASubscriber` | Built-in event subscribers |
| `ExtensionManager` | Unified extension point management |
| `AsyncTaskManager` | Background module execution with status tracking |
| `CancelToken` | Cooperative cancellation token |
| `BindingLoader` | Load modules from YAML binding files |

## Documentation

For full documentation, including Quick Start guides for both Python and TypeScript, visit:
**[https://aipartnerup.github.io/apcore/getting-started.html](https://aipartnerup.github.io/apcore/getting-started.html)**

## Requirements

- Python >= 3.11

## Installation

```bash
pip install apcore
```

### Development

```bash
pip install -e ".[dev]"
```

## Quick Start

### Simple usage (Global Client)

For simple scripts or prototypes, you can use the global `apcore` functions:

```python
import apcore

@apcore.module(id="math.add", description="Add two integers")
def add(a: int, b: int) -> int:
    return a + b

# Directly call it
result = apcore.call("math.add", {"a": 10, "b": 5})
print(result)  # {'result': 15}
```

### Simplified Client (Recommended)

The `APCore` client provides a unified entry point that manages everything for you:

```python
from apcore import APCore

client = APCore()

@client.module(id="math.add", description="Add two integers")
def add(a: int, b: int) -> int:
    return a + b

# Call the module
result = client.call("math.add", {"a": 10, "b": 5})
print(result)  # {'result': 15}
```

### Advanced: Define a module with a class

```python
from pydantic import BaseModel
from apcore import Context, APCore

client = APCore()

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

client.register("greet", GreetModule())
result = client.call("greet", {"name": "Alice"})
# {"message": "Hello, Alice!"}
```

### Add middleware

```python
from apcore import LoggingMiddleware, TracingMiddleware

client.use(LoggingMiddleware())
client.use(TracingMiddleware())
```


### Access control

```python
from apcore import ACL, ACLRule, Executor, Registry

registry = Registry()
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
