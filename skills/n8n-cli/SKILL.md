---
name: n8n-cli
description: Manage n8n credentials, workflows (full JSON), executions, and data tables. Use for n8n API operations like credential CRUD, surgical workflow edits, and execution debugging.
---

# Usage

- Default output is LLM-friendly text. Add `-j`/`--json` for JSON.
- Requires `N8N_API_URL` + `N8N_API_KEY` env vars, or `~/.config/n8n-cli/config.json`
  with `api_key_command` / `api_url_command` for password manager integration.
- `workflow get` always outputs full JSON (for round-trip editing).
- Filter syntax for datatable: `{"type":"and","filters":[{"columnName":"col","condition":"eq","value":"val"}]}`
  Conditions: `eq`, `neq`, `like`, `ilike`, `gt`, `gte`, `lt`, `lte`.

```bash
# Credentials
n8n-cli credential list
n8n-cli credential get <id>
n8n-cli credential create cred.json    # or pipe: echo '{...}' | n8n-cli credential create -
n8n-cli credential update <id> cred.json
n8n-cli credential delete <id>
n8n-cli credential test <id>
n8n-cli credential schema httpBasicAuth

# Workflows (get → edit → put round-trip)
n8n-cli workflow get <id> > wf.json
n8n-cli workflow update <id> wf.json   # strips id/tags/shared/pinData automatically
n8n-cli workflow activate <id>
n8n-cli workflow deactivate <id>

# Executions
n8n-cli execution get <id>             # full runData with per-node errors
n8n-cli execution list --workflow <id> --status error --limit 5

# Data tables
n8n-cli datatable list
n8n-cli datatable get <id>
n8n-cli datatable create table.json    # {"name":"t","columns":[{"name":"c","type":"string"}]}
n8n-cli datatable update <id> new-name
n8n-cli datatable delete <id>
n8n-cli datatable rows <id> --filter '<json>' --sort col:asc --search text --limit 20
n8n-cli datatable insert <id> rows.json --return count|id|all
n8n-cli datatable update-rows <id> body.json   # {"filter":{...},"data":{...}}
n8n-cli datatable upsert <id> body.json        # {"filter":{...},"data":{...}}
n8n-cli datatable delete-rows <id> --filter '<json>' [--dry-run]

# Raw API (escape hatch, always JSON)
n8n-cli raw GET /workflows
n8n-cli raw POST /path body.json
```

See [README.md](../../n8n-cli/README.md) for full documentation.
