"""CLI entry point for tasker-cli."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from tasker_cli.adb import AdbError, trigger_task
from tasker_cli.config import Config
from tasker_cli.specs import (
    SpecsCache,
    action_def_to_wire,
    cache_dir,
    sync_specs,
    validate_task_actions,
)
from tasker_cli.webui import TaskEditor, WebUIClient, WebUIError


@dataclass
class HostOpts:
    """Common options for commands that talk to the WebUI."""

    host: str | None
    port: int | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> HostOpts:
        return cls(host=args.host, port=args.port)

    def config(self) -> Config:
        return Config.from_env(host_override=self.host, port_override=self.port)

    def client(self) -> WebUIClient:
        return WebUIClient(self.config().base_url)


@dataclass
class DeployOpts:
    """Options for the deploy command."""

    host_opts: HostOpts
    file: str
    dry_run: bool
    replace: bool
    append: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> DeployOpts:
        return cls(
            host_opts=HostOpts.from_args(args),
            file=args.file,
            dry_run=args.dry_run,
            replace=args.replace,
            append=args.append,
        )


@dataclass
class TriggerOpts:
    """Options for the trigger command."""

    task_name: str
    host: str | None
    par1: str | None
    par2: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> TriggerOpts:
        return cls(
            task_name=args.task_name,
            host=args.host,
            par1=args.par1,
            par2=args.par2,
        )


@dataclass
class SpecsOpts:
    """Options for the specs command."""

    search: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> SpecsOpts:
        return cls(search=args.search)


def cmd_ping(args: argparse.Namespace) -> None:
    """Check WebUI connectivity."""
    opts = HostOpts.from_args(args)
    cfg = opts.config()
    client = opts.client()
    if client.ping():
        print(f"✓ WebUI reachable at {cfg.host}:{cfg.webui_port}")
    else:
        print(f"✗ WebUI not reachable at {cfg.host}:{cfg.webui_port}")
        raise SystemExit(1)


def cmd_sync_specs(args: argparse.Namespace) -> None:
    """Fetch and cache specs from the WebUI."""
    opts = HostOpts.from_args(args)
    client = opts.client()
    specs = sync_specs(client)
    print(
        f"Fetched {len(specs.actions)} action specs, "
        f"{len(specs.arg_types)} arg types, "
        f"{len(specs.categories)} categories"
    )
    print(f"Cached to {cache_dir()}")


def cmd_specs(args: argparse.Namespace) -> None:
    """Search available action specs."""
    opts = SpecsOpts.from_args(args)
    specs = SpecsCache.load()

    if opts.search:
        results = specs.search(opts.search)
        if not results:
            print(f"No actions matching '{opts.search}'")
            return
        for spec in sorted(results, key=lambda s: s.name):
            print(specs.format_action_spec(spec))
            print()
    else:
        for spec in sorted(specs.actions.values(), key=lambda s: s.name):
            cat_name = specs.categories.get(spec.category, "Unknown")
            print(f"  {spec.name} (code {spec.code}, {cat_name})")


def cmd_show(args: argparse.Namespace) -> None:
    """Show actions in the currently-edited task."""
    opts = HostOpts.from_args(args)
    client = opts.client()
    specs = SpecsCache.load()

    actions = client.get_actions()
    if not actions:
        print("(no actions)")
        return

    for i, action in enumerate(actions):
        _print_action(i, action, specs)


def _print_action(index: int, action: dict[str, Any], specs: SpecsCache) -> None:
    """Format and print a single action from the WebUI."""
    code = action.get("code", 0)
    action_spec = None
    for spec in specs.actions.values():
        if spec.code == code:
            action_spec = spec
            break

    name = action_spec.name if action_spec else f"Unknown({code})"

    raw_args = action.get("args", [])
    arg_parts: list[str] = []
    if isinstance(raw_args, list):
        for arg in raw_args:
            if not isinstance(arg, dict):
                continue
            arg_id = arg.get("id", 0)
            arg_value = arg.get("value", "")
            if arg_value == "" or arg_value is None:
                continue
            arg_name = str(arg_id)
            if action_spec:
                for aspec in action_spec.args:
                    if aspec.arg_id == arg_id:
                        arg_name = aspec.name
                        break
            arg_parts.append(f"{arg_name}={arg_value}")

    args_str = "  " + "  ".join(arg_parts) if arg_parts else ""
    print(f"{index}: {name}{args_str}")


def _load_task_def(source: str) -> dict[str, Any]:
    """Load a task definition from a file path or stdin."""
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text(encoding="utf-8")

    try:
        task_def: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON: {e}"
        raise SystemExit(msg) from e

    return task_def


def _deploy_actions(
    client: TaskEditor,
    specs: SpecsCache,
    actions: list[dict[str, Any]],
    *,
    append: bool,
) -> None:
    """Deploy pre-validated actions to the WebUI."""
    existing = client.get_actions()
    if existing and not append:
        print(f"Clearing {len(existing)} existing actions...")
        for i in range(len(existing) - 1, -1, -1):
            client.delete_action(i)
        existing = []

    # Convert all actions to wire format before sending anything,
    # so a conversion error doesn't leave a half-deployed task
    wire_actions = [action_def_to_wire(a, specs) for a in actions]

    print(f"Deploying {len(wire_actions)} actions...")
    deployed_count = 0
    try:
        for wire in wire_actions:
            client.append_action(wire)
            deployed_count += 1
    except WebUIError as e:
        print(f"  ✗ Failed at action {deployed_count}: {e}")
        if deployed_count > 0:
            rollback_start = len(existing)
            print(f"  Rolling back {deployed_count} actions...")
            for i in range(rollback_start + deployed_count - 1, rollback_start - 1, -1):
                with contextlib.suppress(WebUIError):
                    client.delete_action(i)
        raise SystemExit(1) from e

    print("  ✓ Done. Save the task in Tasker.")


def cmd_deploy(args: argparse.Namespace) -> None:
    """Deploy a task definition to the currently-edited task."""
    opts = DeployOpts.from_args(args)
    cfg = opts.host_opts.config()
    client = WebUIClient(cfg.base_url)
    specs = SpecsCache.load()

    task_def = _load_task_def(opts.file)
    raw_actions = task_def.get("actions", [])
    if not isinstance(raw_actions, list):
        msg = "'actions' must be a list"
        raise SystemExit(msg)

    # Validate
    print(f"Validating {len(raw_actions)} actions against specs...")
    errors = validate_task_actions(task_def, specs)
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        raise SystemExit(1)

    # All validated — safe to cast
    actions: list[dict[str, Any]] = raw_actions

    for action_def in actions:
        action_name = str(action_def.get("action", "?"))
        arg_count = len(action_def.get("args", {}))
        arg_word = "arg" if arg_count == 1 else "args"
        print(f"  ✓ {action_name} ({arg_count} {arg_word})")

    if opts.dry_run:
        print("Dry run — not deploying.")
        return

    # Check existing actions
    existing = client.get_actions()
    if existing and not opts.replace and not opts.append:
        print(
            f"Task has {len(existing)} existing actions. "
            "Use --replace to clear or --append to keep them."
        )
        raise SystemExit(1)

    _deploy_actions(client, specs, actions, append=opts.append)


def cmd_trigger(args: argparse.Namespace) -> None:
    """Trigger a named task via adb broadcast."""
    opts = TriggerOpts.from_args(args)
    host = opts.host if opts.host is not None else os.environ.get("TASKER_HOST")
    adb_port = os.environ.get("TASKER_ADB_PORT")
    adb_target = f"{host}:{adb_port}" if host and adb_port else None

    try:
        trigger_task(
            opts.task_name,
            par1=opts.par1,
            par2=opts.par2,
            adb_target=adb_target,
        )
    except AdbError as e:
        print(f"✗ {e}")
        raise SystemExit(1) from e


def _add_host_args(parser: argparse.ArgumentParser) -> None:
    """Add --host and --port arguments to a subparser."""
    parser.add_argument("--host", help="Phone IP (default: $TASKER_HOST)")
    parser.add_argument("--port", type=int, help="WebUI port (default: 8745)")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="tasker-cli",
        description="Deploy and trigger Tasker tasks via WebUI and adb",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ping = sub.add_parser("ping", help="Check WebUI connectivity")
    _add_host_args(p_ping)

    p_sync = sub.add_parser("sync-specs", help="Fetch and cache action specs")
    _add_host_args(p_sync)

    p_specs = sub.add_parser("specs", help="Search action specs")
    p_specs.add_argument("--search", "-s", help="Search term")

    p_show = sub.add_parser("show", help="Show current task actions")
    _add_host_args(p_show)

    p_deploy = sub.add_parser("deploy", help="Deploy task definition")
    p_deploy.add_argument("file", help="JSON file (or - for stdin)")
    _add_host_args(p_deploy)
    p_deploy.add_argument("--dry-run", action="store_true", help="Validate only")
    mode = p_deploy.add_mutually_exclusive_group()
    mode.add_argument(
        "--replace", action="store_true", help="Clear existing actions first"
    )
    mode.add_argument("--append", action="store_true", help="Keep existing actions")

    p_trigger = sub.add_parser("trigger", help="Trigger task via adb")
    p_trigger.add_argument("task_name", help="Task name to trigger")
    p_trigger.add_argument("--host", help="Phone IP (for adb target)")
    p_trigger.add_argument("--par1", help="Parameter 1")
    p_trigger.add_argument("--par2", help="Parameter 2")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    commands: dict[str, Callable[[argparse.Namespace], None]] = {
        "ping": cmd_ping,
        "sync-specs": cmd_sync_specs,
        "specs": cmd_specs,
        "show": cmd_show,
        "deploy": cmd_deploy,
        "trigger": cmd_trigger,
    }

    cmd_func = commands.get(args.command)
    if cmd_func is None:
        parser.print_help()
        raise SystemExit(1)

    cmd_func(args)


if __name__ == "__main__":
    main()
