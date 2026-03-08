"""Action spec caching, validation, and search."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from tasker_cli.webui import WebUIClient


class ArgType(IntEnum):
    """Tasker action argument types from /arg_specs."""

    INT = 0
    STRING = 1
    APP = 2
    BOOLEAN = 3
    ICON = 4
    BUNDLE = 5  # Read-only output variables — skip when creating
    SCENE = 6


def cache_dir() -> Path:
    """Return the XDG cache directory for tasker-cli."""
    xdg = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(xdg) / "tasker-cli"


@dataclass
class ArgSpec:
    """Specification for an action argument."""

    arg_id: int
    name: str
    arg_type: ArgType
    mandatory: bool
    spec: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ArgSpec:
        return cls(
            arg_id=int(d.get("id", 0)),
            name=str(d.get("name", "")),
            arg_type=ArgType(int(d.get("type", 0))),
            mandatory=bool(d.get("isMandatory", False)),
            spec=str(d.get("spec", "")),
        )


@dataclass
class ActionSpec:
    """Specification for a Tasker action."""

    code: int
    name: str
    category: int
    args: list[ArgSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActionSpec:
        raw_args = d.get("args", [])
        args = (
            [ArgSpec.from_dict(a) for a in raw_args]
            if isinstance(raw_args, list)
            else []
        )
        return cls(
            code=int(d.get("code", 0)),
            name=str(d.get("name", "")),
            category=int(d.get("categoryCode", d.get("category", 0))),
            args=args,
        )

    def arg_by_name(self, name: str) -> ArgSpec | None:
        """Find an arg spec by name (case-insensitive)."""
        name_lower = name.lower()
        for arg in self.args:
            if arg.name.lower() == name_lower:
                return arg
        return None


@dataclass
class SpecsCache:
    """Cached action/arg/category specs from the WebUI."""

    actions: dict[str, ActionSpec]  # name (lowercase) -> ActionSpec
    arg_types: dict[int, str]  # type id -> type name
    categories: dict[int, str]  # category id -> category name

    @classmethod
    def load(cls) -> SpecsCache:
        """Load specs from the cache directory."""
        cache = cache_dir()
        try:
            action_specs_raw = json.loads(
                (cache / "action_specs.json").read_text(encoding="utf-8")
            )
            arg_specs_raw = json.loads(
                (cache / "arg_specs.json").read_text(encoding="utf-8")
            )
            category_specs_raw = json.loads(
                (cache / "category_specs.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError as e:
            msg = (
                "Specs not cached. Run 'tasker-cli sync-specs' first.\n"
                f"Missing: {e.filename}"
            )
            raise SystemExit(msg) from e

        return cls._parse(action_specs_raw, arg_specs_raw, category_specs_raw)

    @classmethod
    def _parse(
        cls,
        action_specs_raw: list[dict[str, Any]],
        arg_specs_raw: dict[str, Any],
        category_specs_raw: list[dict[str, Any]],
    ) -> SpecsCache:
        actions: dict[str, ActionSpec] = {}
        for raw in action_specs_raw:
            spec = ActionSpec.from_dict(raw)
            actions[spec.name.lower()] = spec

        arg_types: dict[int, str] = {}
        for key, val in arg_specs_raw.items():
            arg_types[int(key)] = str(val)

        categories: dict[int, str] = {}
        for raw in category_specs_raw:
            cat_id = int(raw.get("code", raw.get("id", 0)))
            cat_name = str(raw.get("name", ""))
            categories[cat_id] = cat_name

        return cls(actions=actions, arg_types=arg_types, categories=categories)

    @classmethod
    def from_raw(
        cls,
        action_specs_raw: list[dict[str, Any]],
        arg_specs_raw: dict[str, Any],
        category_specs_raw: list[dict[str, Any]],
    ) -> SpecsCache:
        """Parse specs from raw API responses (for testing)."""
        return cls._parse(action_specs_raw, arg_specs_raw, category_specs_raw)

    def find_action(self, name: str) -> ActionSpec | None:
        """Find an action spec by name (case-insensitive)."""
        return self.actions.get(name.lower())

    def search(self, term: str) -> list[ActionSpec]:
        """Search actions by name substring (case-insensitive)."""
        term_lower = term.lower()
        return [
            spec for spec in self.actions.values() if term_lower in spec.name.lower()
        ]

    def format_action_spec(self, spec: ActionSpec) -> str:
        """Format an action spec for display."""
        cat_name = self.categories.get(spec.category, "Unknown")
        lines = [f"{spec.name} (code {spec.code}, category: {cat_name})"]
        for arg in spec.args:
            type_name = self.arg_types.get(arg.arg_type, f"type{arg.arg_type}")
            required = ", required" if arg.mandatory else ""
            constraint = f", spec={arg.spec}" if arg.spec else ""
            lines.append(f"  {arg.name:<20} [{type_name}{required}{constraint}]")
        return "\n".join(lines)


def sync_specs(client: WebUIClient) -> SpecsCache:
    """Fetch specs from WebUI and save to cache."""
    action_specs_raw = client.get_action_specs()
    arg_specs_raw = client.get_arg_specs()
    category_specs_raw = client.get_category_specs()

    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "action_specs.json").write_text(
        json.dumps(action_specs_raw, indent=2), encoding="utf-8"
    )
    (cache / "arg_specs.json").write_text(
        json.dumps(arg_specs_raw, indent=2), encoding="utf-8"
    )
    (cache / "category_specs.json").write_text(
        json.dumps(category_specs_raw, indent=2), encoding="utf-8"
    )

    return SpecsCache.from_raw(
        cast("list[dict[str, Any]]", action_specs_raw),
        cast("dict[str, Any]", arg_specs_raw),
        cast("list[dict[str, Any]]", category_specs_raw),
    )


@dataclass
class ValidationError:
    """A single validation error."""

    action_index: int
    action_name: str
    message: str

    def __str__(self) -> str:
        return f"Action {self.action_index} ({self.action_name}): {self.message}"


def _arg_present(arg_spec: ArgSpec, args: dict[str, Any]) -> bool:
    """Check if an arg is present in the provided args dict (case-insensitive)."""
    return any(k.lower() == arg_spec.name.lower() for k in args)


def validate_task_actions(
    task_def: dict[str, Any],
    specs: SpecsCache,
) -> list[ValidationError]:
    """Validate a task definition JSON against cached specs.

    Returns a list of validation errors (empty if valid).
    """
    errors: list[ValidationError] = []
    actions = task_def.get("actions", [])

    if not isinstance(actions, list):
        errors.append(ValidationError(0, "<root>", "'actions' must be a list"))
        return errors

    for i, action_def in enumerate(actions):
        if not isinstance(action_def, dict):
            errors.append(ValidationError(i, "<invalid>", "Action must be an object"))
            continue

        action_name = str(action_def.get("action", ""))
        if not action_name:
            errors.append(ValidationError(i, "<missing>", "Missing 'action' field"))
            continue

        action_spec = specs.find_action(action_name)
        if action_spec is None:
            errors.append(
                ValidationError(i, action_name, f"Unknown action: {action_name}")
            )
            continue

        args = action_def.get("args", {})
        if not isinstance(args, dict):
            errors.append(ValidationError(i, action_name, "'args' must be an object"))
            continue

        # Check each provided arg exists in the spec
        unknown = [
            ValidationError(i, action_name, f"Unknown arg: {arg_name}")
            for arg_name in args
            if action_spec.arg_by_name(str(arg_name)) is None
        ]
        errors.extend(unknown)

        # Check mandatory args are present
        # Skip Bundle (read-only output) and Boolean (has implicit defaults)
        missing = [
            ValidationError(i, action_name, f"Missing required arg: {arg.name}")
            for arg in action_spec.args
            if arg.mandatory
            and arg.arg_type not in (ArgType.BUNDLE, ArgType.BOOLEAN)
            and not _arg_present(arg, args)
        ]
        errors.extend(missing)

    return errors


def _coerce_bool(value: Any) -> bool:  # noqa: ANN401
    """Coerce a value to a JSON boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _coerce_value(value: Any, arg_type: ArgType) -> str | int | bool:  # noqa: ANN401
    """Coerce a value to the correct wire type based on arg spec type.

    Booleans must be actual JSON booleans. Ints can be strings or ints.
    Everything else is a string.
    """
    if arg_type == ArgType.BOOLEAN:
        return _coerce_bool(value)
    if arg_type == ArgType.INT:
        # bool is a subclass of int — must check first to avoid True → true
        return int(value) if isinstance(value, (bool, int)) else str(value)
    return str(value)


def action_def_to_wire(
    action_def: dict[str, Any],
    specs: SpecsCache,
) -> dict[str, Any]:
    """Convert a human-readable action definition to WebUI wire format.

    Maps action name to code and arg names to IDs. Coerces values by type:
    booleans → JSON bool, ints → int or string, everything else → string.
    The result is wrapped in {"action": ...} as required by the WebUI.
    """
    action_name = str(action_def["action"])
    action_spec = specs.find_action(action_name)
    if action_spec is None:
        msg = f"Unknown action: {action_name}"
        raise ValueError(msg)

    args = action_def.get("args", {})
    if not isinstance(args, dict):
        msg = f"'args' must be an object for action '{action_name}'"
        raise TypeError(msg)

    wire_args: list[dict[str, Any]] = []

    for arg_name, arg_value in args.items():
        arg_spec = action_spec.arg_by_name(str(arg_name))
        if arg_spec is None:
            msg = f"Unknown arg '{arg_name}' for action '{action_name}'"
            raise ValueError(msg)

        wire_args.append(
            {
                "id": arg_spec.arg_id,
                "value": _coerce_value(arg_value, arg_spec.arg_type),
            }
        )

    inner: dict[str, Any] = {
        "code": action_spec.code,
        "args": wire_args,
    }

    # Pass through conditions if present
    if "condition" in action_def:
        inner["condition"] = action_def["condition"]

    return {"action": inner}
