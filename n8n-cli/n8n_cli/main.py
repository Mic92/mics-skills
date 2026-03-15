"""CLI entry point and command dispatch."""

import argparse
import sys
from collections.abc import Callable

from n8n_cli.client import Client
from n8n_cli.commands import (
    apply,
    credential,
    datatable,
    execution,
    import_wf,
    raw,
    tag,
    test_wf,
    workflow,
)
from n8n_cli.config import CONFIG_FILE, resolve_credentials
from n8n_cli.errors import CLIError, ConfigError

Handler = Callable[[Client, argparse.Namespace], None]


def _make_client() -> Client:
    """Create a client from environment variables or config file."""
    api_url, api_key, timeout = resolve_credentials()
    if not api_url or not api_key:
        missing = []
        if not api_url:
            missing.append("N8N_API_URL")
        if not api_key:
            missing.append("N8N_API_KEY")
        raise ConfigError(f"{', '.join(missing)} not set. Set env vars or configure {CONFIG_FILE}")
    return Client(api_url, api_key, timeout)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="n8n-cli", description="Python CLI for n8n API")
    p.add_argument("-j", "--json", action="store_true", dest="use_json", help="Output JSON")
    sub = p.add_subparsers(dest="command")

    # -- credential ----------------------------------------------------------
    cred = sub.add_parser("credential", help="Manage credentials")
    cred_sub = cred.add_subparsers(dest="subcmd")

    cred_sub.add_parser("list", help="List all credentials")

    s = cred_sub.add_parser("get", help="Get credential metadata")
    s.add_argument("id", help="Credential ID")

    s = cred_sub.add_parser("create", help="Create credential from JSON")
    s.add_argument("file", help="JSON file or - for stdin")

    s = cred_sub.add_parser("update", help="Update credential")
    s.add_argument("id", help="Credential ID")
    s.add_argument("file", help="JSON file or - for stdin")

    s = cred_sub.add_parser("delete", help="Delete credential")
    s.add_argument("id", help="Credential ID")

    s = cred_sub.add_parser("test", help="Test credential")
    s.add_argument("id", help="Credential ID")

    s = cred_sub.add_parser("schema", help="Get credential type schema")
    s.add_argument("type", help="Credential type name")

    # -- workflow -------------------------------------------------------------
    wf = sub.add_parser("workflow", help="Manage workflows")
    wf_sub = wf.add_subparsers(dest="subcmd")

    s = wf_sub.add_parser("list", help="List all workflows")
    active_grp = s.add_mutually_exclusive_group()
    active_grp.add_argument("--active", dest="active", action="store_true", default=None)
    active_grp.add_argument("--inactive", dest="active", action="store_false")
    s.add_argument("--tags", help="Filter by tags (comma-separated)")
    s.add_argument("--name", help="Filter by name (substring match)")
    s.add_argument("--limit", type=int, help="Max results")

    s = wf_sub.add_parser("get", help="Get full workflow JSON")
    s.add_argument("id", help="Workflow ID")

    s = wf_sub.add_parser("create", help="Create workflow from JSON")
    s.add_argument("file", help="JSON file or - for stdin")

    s = wf_sub.add_parser("update", help="Update workflow from JSON")
    s.add_argument("id", help="Workflow ID")
    s.add_argument("file", help="JSON file or - for stdin")

    s = wf_sub.add_parser("delete", help="Delete workflow")
    s.add_argument("id", help="Workflow ID")

    s = wf_sub.add_parser("activate", help="Activate workflow")
    s.add_argument("id", help="Workflow ID")

    s = wf_sub.add_parser("deactivate", help="Deactivate workflow")
    s.add_argument("id", help="Workflow ID")

    # -- execution ------------------------------------------------------------
    exc = sub.add_parser("execution", help="Manage executions")
    exc_sub = exc.add_subparsers(dest="subcmd")

    s = exc_sub.add_parser("get", help="Get execution details")
    s.add_argument("id", help="Execution ID")
    s.add_argument("--show-data", action="store_true", help="Include full execution data in output")

    s = exc_sub.add_parser("list", help="List executions")
    s.add_argument("--workflow", help="Filter by workflow ID")
    s.add_argument("--status", help="Filter by status")
    s.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    s = exc_sub.add_parser("delete", help="Delete execution")
    s.add_argument("id", help="Execution ID")

    s = exc_sub.add_parser("retry", help="Retry a failed execution")
    s.add_argument("id", help="Execution ID")
    s.add_argument(
        "--load-workflow", action="store_true", help="Retry with latest workflow version"
    )

    s = exc_sub.add_parser("stop", help="Stop a running execution")
    s.add_argument("id", help="Execution ID")

    # -- datatable ------------------------------------------------------------
    dt = sub.add_parser("datatable", help="Manage data tables")
    dt_sub = dt.add_subparsers(dest="subcmd")

    s = dt_sub.add_parser("list", help="List all data tables")
    s.add_argument("--filter", help="Filter conditions (JSON)")
    s.add_argument("--sort", help="Sort: field:asc or field:desc")
    s.add_argument("--limit", type=int, help="Max results")

    s = dt_sub.add_parser("get", help="Get data table by ID")
    s.add_argument("id", help="Data table ID")

    s = dt_sub.add_parser("create", help="Create data table from JSON")
    s.add_argument("file", help="JSON file or - for stdin")

    s = dt_sub.add_parser("update", help="Rename data table")
    s.add_argument("id", help="Data table ID")
    s.add_argument("name", help="New name")

    s = dt_sub.add_parser("delete", help="Delete data table")
    s.add_argument("id", help="Data table ID")

    s = dt_sub.add_parser("rows", help="List rows")
    s.add_argument("id", help="Data table ID")
    s.add_argument("--filter", help="Filter conditions (JSON)")
    s.add_argument("--sort", help="Sort: col:asc or col:desc")
    s.add_argument("--search", help="Full-text search")
    s.add_argument("--limit", type=int, help="Max results")

    s = dt_sub.add_parser("insert", help="Insert rows from JSON")
    s.add_argument("id", help="Data table ID")
    s.add_argument("file", help="JSON file or - for stdin")
    s.add_argument(
        "--return",
        dest="return_type",
        default="count",
        choices=["count", "id", "all"],
        help="Return type (default: count)",
    )

    s = dt_sub.add_parser("update-rows", help="Update rows matching filter")
    s.add_argument("id", help="Data table ID")
    s.add_argument("file", help="JSON file or - for stdin")

    s = dt_sub.add_parser("upsert", help="Upsert a row")
    s.add_argument("id", help="Data table ID")
    s.add_argument("file", help="JSON file or - for stdin")

    s = dt_sub.add_parser("delete-rows", help="Delete rows matching filter")
    s.add_argument("id", help="Data table ID")
    s.add_argument("--filter", required=True, help="Filter conditions (JSON, required)")
    s.add_argument("--return-data", action="store_true", help="Return deleted rows")
    s.add_argument("--dry-run", action="store_true", help="Preview without deleting")

    # -- tag ------------------------------------------------------------------
    tg = sub.add_parser("tag", help="Manage tags")
    tg_sub = tg.add_subparsers(dest="subcmd")

    tg_sub.add_parser("list", help="List all tags")

    s = tg_sub.add_parser("get", help="Get tag by ID")
    s.add_argument("id", help="Tag ID")

    s = tg_sub.add_parser("create", help="Create a tag")
    s.add_argument("name", help="Tag name")

    s = tg_sub.add_parser("update", help="Update a tag name")
    s.add_argument("id", help="Tag ID")
    s.add_argument("name", help="New tag name")

    s = tg_sub.add_parser("delete", help="Delete a tag")
    s.add_argument("id", help="Tag ID")

    # -- raw ------------------------------------------------------------------
    s = sub.add_parser("raw", help="Raw API call (escape hatch)")
    s.add_argument("method", metavar="METHOD", help="HTTP method")
    s.add_argument("path", metavar="PATH", help="API path")
    s.add_argument("file", nargs="?", metavar="FILE", help="JSON body file or - for stdin")

    # -- test -----------------------------------------------------------------
    s = sub.add_parser("test", help="Test a workflow via its webhook")
    s.add_argument("id", help="Workflow ID")
    s.add_argument("-d", "--data", help="JSON data to send to the webhook")
    s.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds (default: 30)")
    s.add_argument(
        "--wait-execution",
        action="store_true",
        help="Wait for execution to complete and show results",
    )
    s.add_argument(
        "--execution-timeout",
        type=int,
        default=300,
        help="Max seconds to wait for execution (default: 300)",
    )
    s.add_argument("--activate", action="store_true", help="Auto-activate the workflow if inactive")
    s.add_argument("--dry-run", action="store_true", help="Show webhook URL without executing")

    # -- import ---------------------------------------------------------------
    s = sub.add_parser("import", help="Import workflows from n8n to local files")
    s.add_argument(
        "-d", "--dir", default="./definitions", help="Target directory (default: ./definitions)"
    )
    s.add_argument("--ids", help="Comma-separated workflow IDs to import (empty = all)")
    s.add_argument("--dry-run", action="store_true", help="Preview without writing files")

    # -- apply ----------------------------------------------------------------
    s = sub.add_parser("apply", help="Apply local workflow files to n8n server")
    s.add_argument(
        "-d",
        "--dir",
        default="./definitions",
        help="Definitions directory (default: ./definitions)",
    )
    s.add_argument("--ids", help="Comma-separated workflow IDs to process")
    s.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    s.add_argument("--force", action="store_true", help="Override conflict detection")

    return p


_HANDLERS: dict[tuple[str, str | None], Handler] = {
    ("credential", "list"): credential.cmd_credential_list,
    ("credential", "get"): credential.cmd_credential_get,
    ("credential", "create"): credential.cmd_credential_create,
    ("credential", "update"): credential.cmd_credential_update,
    ("credential", "delete"): credential.cmd_credential_delete,
    ("credential", "test"): credential.cmd_credential_test,
    ("credential", "schema"): credential.cmd_credential_schema,
    ("workflow", "list"): workflow.cmd_workflow_list,
    ("workflow", "get"): workflow.cmd_workflow_get,
    ("workflow", "create"): workflow.cmd_workflow_create,
    ("workflow", "update"): workflow.cmd_workflow_update,
    ("workflow", "delete"): workflow.cmd_workflow_delete,
    ("workflow", "activate"): workflow.cmd_workflow_activate,
    ("workflow", "deactivate"): workflow.cmd_workflow_deactivate,
    ("execution", "get"): execution.cmd_execution_get,
    ("execution", "list"): execution.cmd_execution_list,
    ("execution", "delete"): execution.cmd_execution_delete,
    ("execution", "retry"): execution.cmd_execution_retry,
    ("execution", "stop"): execution.cmd_execution_stop,
    ("tag", "list"): tag.cmd_tag_list,
    ("tag", "get"): tag.cmd_tag_get,
    ("tag", "create"): tag.cmd_tag_create,
    ("tag", "update"): tag.cmd_tag_update,
    ("tag", "delete"): tag.cmd_tag_delete,
    ("datatable", "list"): datatable.cmd_datatable_list,
    ("datatable", "get"): datatable.cmd_datatable_get,
    ("datatable", "create"): datatable.cmd_datatable_create,
    ("datatable", "update"): datatable.cmd_datatable_update,
    ("datatable", "delete"): datatable.cmd_datatable_delete,
    ("datatable", "rows"): datatable.cmd_datatable_rows,
    ("datatable", "insert"): datatable.cmd_datatable_insert,
    ("datatable", "update-rows"): datatable.cmd_datatable_update_rows,
    ("datatable", "upsert"): datatable.cmd_datatable_upsert,
    ("datatable", "delete-rows"): datatable.cmd_datatable_delete_rows,
    ("raw", None): raw.cmd_raw,
    ("test", None): test_wf.cmd_test,
    ("import", None): import_wf.cmd_import,
    ("apply", None): apply.cmd_apply,
}


def main() -> None:
    parser = _build_parser()
    ns = parser.parse_args()

    if not ns.command:
        parser.print_help()
        sys.exit(0)

    # For grouped commands, check subcmd
    key = (ns.command, getattr(ns, "subcmd", None))
    handler = _HANDLERS.get(key)
    if handler is None:
        # subcmd missing — print subcommand help
        parser.parse_args([ns.command, "--help"])
        return

    try:
        client = _make_client()
        handler(client, ns)
    except CLIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
