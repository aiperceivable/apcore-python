"""Central module registry for discovering, registering, and querying modules."""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Protocol, runtime_checkable

from apcore.errors import (
    InvalidInputError,
    ModuleNotFoundError,
)
from apcore.registry.dependencies import resolve_dependencies
from apcore.registry.entry_point import resolve_entry_point
from apcore.registry.metadata import (
    load_id_map,
    load_metadata,
    merge_module_metadata,
    parse_dependencies,
)
from apcore.registry.scanner import scan_extensions, scan_multi_root
from apcore.registry.types import DependencyInfo, ModuleDescriptor
from apcore.registry.validation import validate_module

if TYPE_CHECKING:
    from apcore.config import Config

logger = logging.getLogger(__name__)

REGISTRY_EVENTS: dict[str, str] = {
    "REGISTER": "register",
    "UNREGISTER": "unregister",
}

MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


@runtime_checkable
class Discoverer(Protocol):
    """Protocol for custom module discovery."""

    def discover(self, roots: list[str]) -> list[dict[str, Any]]:
        """Discover modules from the given root directories.

        Returns:
            List of dicts with at least 'module_id' and 'module' keys.
        """
        ...


@runtime_checkable
class ModuleValidator(Protocol):
    """Protocol for custom module validation."""

    def validate(self, module: Any) -> list[str]:
        """Validate a module.

        Returns:
            List of error strings. Empty list means valid.
        """
        ...


MAX_MODULE_ID_LENGTH = 128

RESERVED_WORDS = frozenset({"system", "internal", "core", "apcore", "plugin", "schema", "acl"})

__all__ = [
    "Registry",
    "REGISTRY_EVENTS",
    "MODULE_ID_PATTERN",
    "MAX_MODULE_ID_LENGTH",
    "RESERVED_WORDS",
    "Discoverer",
    "ModuleValidator",
]


class Registry:
    """Central module registry for discovering, registering, and querying modules."""

    def __init__(
        self,
        config: Config | None = None,
        extensions_dir: str | None = None,
        extensions_dirs: list[str | dict] | None = None,
        id_map_path: str | None = None,
    ) -> None:
        """Initialize the Registry.

        Args:
            config: Optional Config object for framework-wide settings.
            extensions_dir: Single extensions directory path.
            extensions_dirs: List of extension root configs (mutually exclusive with extensions_dir).
            id_map_path: Path to ID Map YAML file for overriding canonical IDs.

        Raises:
            InvalidInputError: If both extensions_dir and extensions_dirs are specified.
        """
        if extensions_dir is not None and extensions_dirs is not None:
            raise InvalidInputError(message="Cannot specify both extensions_dir and extensions_dirs")

        # Determine extension roots: individual params > config > defaults
        if extensions_dir is not None:
            self._extension_roots: list[dict[str, Any]] = [{"root": extensions_dir}]
        elif extensions_dirs is not None:
            self._extension_roots = [{"root": item} if isinstance(item, str) else item for item in extensions_dirs]
        elif config is not None:
            ext_root = config.get("extensions.root")
            if ext_root:
                self._extension_roots = [{"root": ext_root}]
            else:
                self._extension_roots = [{"root": "./extensions"}]
        else:
            self._extension_roots = [{"root": "./extensions"}]

        # Internal state
        self._modules: dict[str, Any] = {}
        self._module_meta: dict[str, dict[str, Any]] = {}
        self._callbacks: dict[str, list[Callable[..., Any]]] = {
            REGISTRY_EVENTS["REGISTER"]: [],
            REGISTRY_EVENTS["UNREGISTER"]: [],
        }
        self._lock = threading.RLock()
        self._id_map: dict[str, dict[str, Any]] = {}
        self._schema_cache: dict[str, dict[str, Any]] = {}
        self._config = config
        self._custom_discoverer: Discoverer | None = None
        self._custom_validator: ModuleValidator | None = None

        # Load ID map if provided
        if id_map_path is not None:
            self._id_map = load_id_map(Path(id_map_path))

    # ----- Custom Discoverer / Validator -----

    def set_discoverer(self, discoverer: Discoverer) -> None:
        """Set a custom module discoverer."""
        self._custom_discoverer = discoverer

    def set_validator(self, validator: ModuleValidator) -> None:
        """Set a custom module validator."""
        self._custom_validator = validator

    # ----- Discovery -----

    def discover(self) -> int:
        """Discover and register modules from configured extension directories.

        If a custom discoverer is set via ``set_discoverer()``, it is used
        instead of the default file-system scanning logic.  If a custom
        validator is set via ``set_validator()``, it replaces the built-in
        ``validate_module()`` check.

        Returns:
            Number of modules successfully registered in this discovery pass.

        Raises:
            CircularDependencyError: If circular dependencies detected among modules.
            ConfigNotFoundError: If a configured extension root does not exist.
        """
        if self._custom_discoverer is not None:
            return self._discover_custom()
        return self._discover_default()

    def _discover_custom(self) -> int:
        """Run discovery using the custom discoverer."""
        assert self._custom_discoverer is not None  # noqa: S101

        root_paths = [str(r["root"]) for r in self._extension_roots]
        custom_modules = self._custom_discoverer.discover(root_paths)

        registered_count = 0
        for entry in custom_modules:
            mod_id: str = entry["module_id"]
            mod: Any = entry["module"]

            # Apply custom validator if set
            if self._custom_validator is not None:
                errors = self._custom_validator.validate(mod)
                if errors:
                    logger.warning(
                        "Custom validator rejected module '%s': %s",
                        mod_id,
                        "; ".join(errors),
                    )
                    continue

            try:
                self.register(mod_id, mod)
                registered_count += 1
            except Exception as e:
                logger.warning("Failed to register custom-discovered module '%s': %s", mod_id, e)

        if registered_count == 0 and custom_modules:
            logger.warning(
                "No modules successfully registered from %d custom-discovered entries",
                len(custom_modules),
            )
        elif registered_count == 0:
            logger.warning("No modules discovered by custom discoverer")

        return registered_count

    def _discover_default(self) -> int:
        """Run discovery using the default file-system scanning logic."""
        # Determine scan params from config
        max_depth = 8
        follow_symlinks = False
        if self._config is not None:
            max_depth = self._config.get("extensions.max_depth", 8)
            follow_symlinks = self._config.get("extensions.follow_symlinks", False)

        # Step 1: Scan extension roots
        has_namespace = any("namespace" in r for r in self._extension_roots)
        if len(self._extension_roots) > 1 or has_namespace:
            discovered = scan_multi_root(
                roots=self._extension_roots,
                max_depth=max_depth,
                follow_symlinks=follow_symlinks,
            )
        else:
            root_path = Path(self._extension_roots[0]["root"])
            discovered = scan_extensions(
                root=root_path,
                max_depth=max_depth,
                follow_symlinks=follow_symlinks,
            )

        # Step 2: Apply ID Map overrides
        if self._id_map:
            resolved_roots = [Path(r["root"]).resolve() for r in self._extension_roots]
            for dm in discovered:
                rel_path = None
                for root in resolved_roots:
                    try:
                        rel_path = str(dm.file_path.relative_to(root))
                        break
                    except ValueError:
                        continue
                if rel_path and rel_path in self._id_map:
                    map_entry = self._id_map[rel_path]
                    dm.canonical_id = map_entry["id"]

        # Step 3: Load metadata for each discovered module
        raw_metadata: dict[str, dict[str, Any]] = {}
        for dm in discovered:
            if dm.meta_path:
                raw_metadata[dm.canonical_id] = load_metadata(dm.meta_path)
            else:
                raw_metadata[dm.canonical_id] = {}

        # Step 4: Resolve entry points
        resolved_classes: dict[str, type] = {}
        for dm in discovered:
            meta = raw_metadata.get(dm.canonical_id, {})
            # Inject class override from ID map
            if dm.canonical_id in self._id_map:
                map_entry = self._id_map[dm.canonical_id]
                if map_entry.get("class"):
                    stem = dm.file_path.stem
                    meta.setdefault("entry_point", f"{stem}:{map_entry['class']}")
            try:
                cls = resolve_entry_point(dm.file_path, meta=meta)
            except Exception as e:
                logger.warning("Failed to resolve entry point for '%s': %s", dm.canonical_id, e)
                continue
            resolved_classes[dm.canonical_id] = cls

        # Step 5: Validate module classes (use custom validator if set)
        valid_classes: dict[str, type] = {}
        for mod_id, cls in resolved_classes.items():
            if self._custom_validator is not None:
                errors = self._custom_validator.validate(cls)
            else:
                errors = validate_module(cls)
            if errors:
                logger.warning("Module '%s' failed validation: %s", mod_id, "; ".join(errors))
                continue
            valid_classes[mod_id] = cls

        # Step 6: Collect dependencies
        modules_with_deps: list[tuple[str, list[DependencyInfo]]] = []
        for mod_id in valid_classes:
            meta = raw_metadata.get(mod_id, {})
            deps_raw = meta.get("dependencies", [])
            deps = parse_dependencies(deps_raw) if deps_raw else []
            modules_with_deps.append((mod_id, deps))

        # Step 7: Resolve dependency order (may raise CircularDependencyError)
        known_ids = {mod_id for mod_id, _ in modules_with_deps}
        load_order = resolve_dependencies(modules_with_deps, known_ids=known_ids)

        # Step 8: Instantiate and register in dependency order
        registered_count = 0
        for mod_id in load_order:
            cls = valid_classes[mod_id]
            meta = raw_metadata.get(mod_id, {})
            try:
                module = cls()
            except Exception as e:
                logger.error("Failed to instantiate module '%s': %s", mod_id, e)
                continue

            merged_meta = merge_module_metadata(cls, meta)

            with self._lock:
                self._modules[mod_id] = module
                self._module_meta[mod_id] = merged_meta

            # Call on_load if available
            if hasattr(module, "on_load") and callable(module.on_load):
                try:
                    module.on_load()
                except Exception as e:
                    logger.error("on_load() failed for module '%s': %s", mod_id, e)
                    with self._lock:
                        self._modules.pop(mod_id, None)
                        self._module_meta.pop(mod_id, None)
                    continue

            self._trigger_event("register", mod_id, module)
            registered_count += 1

        if registered_count == 0 and discovered:
            logger.warning(
                "No modules successfully registered from %d discovered files",
                len(discovered),
            )
        elif registered_count == 0:
            logger.warning("No modules discovered")

        return registered_count

    # ----- Manual Registration -----

    def register(self, module_id: str, module: Any) -> None:
        """Manually register a module instance.

        Args:
            module_id: Unique identifier for the module.
            module: Module instance to register.

        Raises:
            InvalidInputError: If module_id is already registered.
            RuntimeError: If module.on_load() fails (propagated).
        """
        if not module_id:
            raise InvalidInputError(message="module_id must be a non-empty string")

        if not MODULE_ID_PATTERN.match(module_id):
            raise InvalidInputError(
                f"Invalid module ID: '{module_id}'. Must match pattern: "
                f"{MODULE_ID_PATTERN.pattern} (lowercase, digits, underscores, dots only; no hyphens)"
            )

        if len(module_id) > MAX_MODULE_ID_LENGTH:
            raise InvalidInputError(f"Module ID exceeds maximum length of {MAX_MODULE_ID_LENGTH}: {len(module_id)}")

        parts = module_id.split(".")
        for part in parts:
            if part in RESERVED_WORDS:
                raise InvalidInputError(f"Module ID contains reserved word: '{part}'")

        with self._lock:
            if module_id in self._modules:
                raise InvalidInputError(message=f"Module already exists: {module_id}")
            self._modules[module_id] = module

        # Call on_load if available
        if hasattr(module, "on_load") and callable(module.on_load):
            try:
                module.on_load()
            except Exception:
                with self._lock:
                    self._modules.pop(module_id, None)
                raise

        self._trigger_event("register", module_id, module)

    def unregister(self, module_id: str) -> bool:
        """Remove a module from the registry.

        Returns False if module was not registered.
        """
        with self._lock:
            if module_id not in self._modules:
                return False
            module = self._modules.pop(module_id)
            self._module_meta.pop(module_id, None)
            self._schema_cache.pop(module_id, None)

        # Call on_unload if available
        if hasattr(module, "on_unload") and callable(module.on_unload):
            try:
                module.on_unload()
            except Exception as e:
                logger.error("on_unload() failed for module '%s': %s", module_id, e)

        self._trigger_event("unregister", module_id, module)
        return True

    # ----- Query Methods -----

    def get(self, module_id: str) -> Any:
        """Look up a module by ID. Returns None if not found.

        Raises:
            ModuleNotFoundError: If module_id is empty string.
        """
        if module_id == "":
            raise ModuleNotFoundError(module_id="")
        with self._lock:
            return self._modules.get(module_id)

    def has(self, module_id: str) -> bool:
        """Check whether a module is registered."""
        with self._lock:
            return module_id in self._modules

    def list(self, tags: list[str] | None = None, prefix: str | None = None) -> list[str]:
        """Return sorted list of registered module IDs, optionally filtered."""
        with self._lock:
            snapshot = dict(self._modules)
            meta_snapshot = dict(self._module_meta)

        ids = list(snapshot.keys())

        if prefix is not None:
            ids = [mid for mid in ids if mid.startswith(prefix)]

        if tags is not None:
            tag_set = set(tags)

            def has_all_tags(mid: str) -> bool:
                mod = snapshot[mid]
                # Check module-level tags attribute
                mod_tags = set(getattr(mod, "tags", []) or [])
                # Also check merged metadata tags
                meta_tags = meta_snapshot.get(mid, {}).get("tags", [])
                if meta_tags:
                    mod_tags.update(meta_tags)
                return tag_set.issubset(mod_tags)

            ids = [mid for mid in ids if has_all_tags(mid)]

        return sorted(ids)

    def iter(self) -> Iterator[tuple[str, Any]]:
        """Return an iterator of (module_id, module) tuples (snapshot-based)."""
        with self._lock:
            items = list(self._modules.items())
        return iter(items)

    @property
    def count(self) -> int:
        """Number of registered modules."""
        with self._lock:
            return len(self._modules)

    @property
    def module_ids(self) -> list[str]:
        """Sorted list of registered module IDs."""
        with self._lock:
            return sorted(self._modules.keys())

    def get_definition(self, module_id: str) -> ModuleDescriptor | None:
        """Get a ModuleDescriptor for a registered module. Returns None if not found."""
        with self._lock:
            module = self._modules.get(module_id)
            if module is None:
                return None
            meta = dict(self._module_meta.get(module_id, {}))

        cls = type(module)

        input_schema_cls = getattr(module, "input_schema", None) or getattr(cls, "input_schema", None)
        output_schema_cls = getattr(module, "output_schema", None) or getattr(cls, "output_schema", None)

        input_json = input_schema_cls.model_json_schema() if input_schema_cls else {}
        output_json = output_schema_cls.model_json_schema() if output_schema_cls else {}

        return ModuleDescriptor(
            module_id=module_id,
            name=meta.get("name") or getattr(module, "name", None),
            description=meta.get("description") or getattr(module, "description", ""),
            documentation=meta.get("documentation") or getattr(module, "documentation", None),
            input_schema=input_json,
            output_schema=output_json,
            version=meta.get("version") or getattr(module, "version", "1.0.0"),
            tags=list(meta.get("tags") or getattr(module, "tags", None) or []),
            annotations=getattr(module, "annotations", None),
            examples=list(getattr(module, "examples", []) or []),
            metadata=meta.get("metadata", {}),
        )

    def describe(self, module_id: str) -> str:
        """Return a human-readable description of a module.

        Args:
            module_id: The ID of the module to describe.

        Returns:
            Markdown-formatted description string.

        Raises:
            ModuleNotFoundError: If module is not registered.
        """
        module = self.get(module_id)
        if module is None:
            raise ModuleNotFoundError(module_id)

        # Check for custom describe method
        if hasattr(module, "describe") and callable(module.describe):
            return str(module.describe())

        # Auto-generate from descriptor
        descriptor = self.get_definition(module_id)
        if descriptor is None:
            return f"Module: {module_id}\n\nNo description available."

        lines = [f"# {descriptor.module_id}"]
        if descriptor.description:
            lines.append(f"\n{descriptor.description}")
        if descriptor.tags:
            lines.append(f"\n**Tags:** {', '.join(descriptor.tags)}")
        if descriptor.input_schema and descriptor.input_schema.get("properties"):
            lines.append("\n**Parameters:**")
            for param, schema in descriptor.input_schema["properties"].items():
                param_type = schema.get("type", "any")
                param_desc = schema.get("description", "")
                required = param in descriptor.input_schema.get("required", [])
                req_marker = " (required)" if required else ""
                lines.append(f"- `{param}` ({param_type}){req_marker}: {param_desc}")
        if descriptor.documentation:
            lines.append(f"\n**Documentation:**\n{descriptor.documentation}")
        return "\n".join(lines)

    # ----- Event System -----

    def on(self, event: str, callback: Callable[..., Any]) -> None:
        """Register an event callback.

        Args:
            event: Event name ('register' or 'unregister').
            callback: Callable(module_id, module) to invoke on the event.

        Raises:
            InvalidInputError: If event name is invalid.
        """
        with self._lock:
            if event not in self._callbacks:
                raise InvalidInputError(message=f"Invalid event: {event}. Must be 'register' or 'unregister'")
            self._callbacks[event].append(callback)

    def _trigger_event(self, event: str, module_id: str, module: Any) -> None:
        """Trigger all callbacks for an event. Errors are logged and swallowed."""
        with self._lock:
            callbacks = list(self._callbacks.get(event, []))
        for cb in callbacks:
            try:
                cb(module_id, module)
            except Exception as e:
                logger.error(
                    "Callback error for event '%s' on module '%s': %s",
                    event,
                    module_id,
                    e,
                )

    # ----- Hot Reload -----

    def watch(self) -> None:
        """Start watching extension directories for file changes.

        Requires the optional ``watchdog`` dependency.
        Raises ImportError if watchdog is not installed.
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            raise ImportError("watchdog is required for hot reload. Install it with: pip install watchdog")

        if hasattr(self, "_observer") and self._observer is not None:
            return  # Already watching

        outer_registry = self

        class _ModuleChangeHandler(FileSystemEventHandler):
            def __init__(self) -> None:
                self._registry = outer_registry
                self._debounce_timer: dict[str, float] = {}

            def _should_process(self, path: str) -> bool:
                if not path.endswith(".py"):
                    return False
                now = __import__("time").time()
                last = self._debounce_timer.get(path, 0.0)
                if now - last < 0.3:
                    return False
                self._debounce_timer[path] = now
                return True

            def on_modified(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return
                path = str(event.src_path)
                if not self._should_process(path):
                    return
                self._registry._handle_file_change(path)

            def on_created(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return
                path = str(event.src_path)
                if not self._should_process(path):
                    return
                self._registry._handle_file_change(path)

            def on_deleted(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return
                path = str(event.src_path)
                if not path.endswith(".py"):
                    return
                self._registry._handle_file_deletion(path)

        self._observer = Observer()
        handler = _ModuleChangeHandler()

        for root_config in self._extension_roots:
            root_path = root_config.get("root", "")
            if root_path and __import__("os").path.isdir(root_path):
                self._observer.schedule(handler, root_path, recursive=True)

        self._observer.start()

    def unwatch(self) -> None:
        """Stop watching extension directories for file changes."""
        if hasattr(self, "_observer") and self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    def _handle_file_change(self, path: str) -> None:
        """Handle a file modification or creation event."""
        import importlib.util
        import os

        # Try to find which module this file belongs to
        module_id = self._path_to_module_id(path)
        if module_id and self.has(module_id):
            # Reload: unregister old, re-discover
            old_module = self.get(module_id)
            if old_module and hasattr(old_module, "on_unload"):
                try:
                    old_module.on_unload()
                except Exception:
                    pass
            self.unregister(module_id)

        # Try to re-import and register
        try:
            spec = importlib.util.spec_from_file_location("_hot_reload", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                # Find module class (look for execute method)
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and hasattr(attr, "execute"):
                        instance = attr()
                        new_id = module_id or os.path.splitext(os.path.basename(path))[0]
                        if self.has(new_id):
                            self.unregister(new_id)
                        self.register(new_id, instance)
                        break
        except Exception as e:
            logger.warning("Hot reload failed for %s: %s", path, e)

    def _handle_file_deletion(self, path: str) -> None:
        """Handle a file deletion event."""
        module_id = self._path_to_module_id(path)
        if module_id and self.has(module_id):
            module = self.get(module_id)
            if module and hasattr(module, "on_unload"):
                try:
                    module.on_unload()
                except Exception:
                    pass
            self.unregister(module_id)

    def _path_to_module_id(self, path: str) -> str | None:
        """Map a file path to a module ID if known."""
        import os

        basename = os.path.splitext(os.path.basename(path))[0]
        # Check if any registered module ID ends with this basename
        for mid in self.module_ids:
            if mid.endswith(basename) or mid == basename:
                return mid
        return None

    # ----- Cache -----

    def clear_cache(self) -> None:
        """Clear the schema cache."""
        with self._lock:
            self._schema_cache.clear()
