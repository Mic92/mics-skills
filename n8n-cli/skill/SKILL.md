---
name: n8n-cli
description: Manage n8n via its REST API. Use when user asks to access n8n.
---

Default output is LLM-friendly text. `-j` for JSON. Use `-` as filename for stdin.
Round-trip editing: `n8n-cli workflow get <id> -j > wf.json` → edit → `n8n-cli workflow update <id> wf.json`.

```bash
# Credentials
n8n-cli credential list
n8n-cli credential get|delete|test <id>
n8n-cli credential create|update <id> cred.json
n8n-cli credential schema httpBasicAuth

# Workflows
n8n-cli workflow list [--active|--inactive] [--tags t1,t2] [--name text] [--limit N]
n8n-cli workflow get <id>              # full JSON, suitable for round-trip
n8n-cli workflow create wf.json
n8n-cli workflow update <id> wf.json   # auto-filters to writable fields
n8n-cli workflow delete|activate|deactivate <id>

# Executions
n8n-cli execution list [--workflow <id>] [--status error] [--limit 5]
n8n-cli execution get <id> [--show-data]
n8n-cli execution delete|stop <id>
n8n-cli execution retry <id> [--load-workflow]

# Tags
n8n-cli tag list
n8n-cli tag create <name>
n8n-cli tag update <id> <new-name>
n8n-cli tag get|delete <id>

# Data tables
n8n-cli datatable list|get|create|update|delete <id> [...]
n8n-cli datatable rows <id> [--filter '<json>' --sort col:asc --limit 20]
n8n-cli datatable insert <id> rows.json [--return count|id|all]
n8n-cli datatable update-rows|upsert <id> body.json  # {"filter":{...},"data":{...}}
n8n-cli datatable delete-rows <id> --filter '<json>' [--dry-run]
# filter: {"type":"and","filters":[{"columnName":"c","condition":"eq","value":"v"}]}

# Test webhook
n8n-cli test <id> [-d '{"key":"val"}'] [--wait-execution] [--activate] [--dry-run]

# Bulk sync (always --dry-run first)
n8n-cli import -d ./definitions [--ids a,b] [--dry-run]           # server → local JSON
n8n-cli apply  -d ./definitions [--ids a,b] [--dry-run] [--force] # local → server

# Raw API escape hatch
n8n-cli raw GET|POST|PUT|DELETE /path [body.json]
```
