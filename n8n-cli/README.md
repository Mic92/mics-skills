# n8n-cli (Python)

Python CLI for n8n API operations — focused on gaps not covered by the
[TypeScript n8n-cli](https://github.com/ubie-oss/n8n-cli):

- **Credential management** — create, get, list, update, delete, test, schema
- **Full workflow JSON round-trip** — get complete JSON, edit, put it back
- **Execution data** — full `runData` with node outputs and per-node errors
- **Data table CRUD** — tables, rows, filtering, upsert
- **Raw API calls** — escape hatch for any n8n API endpoint

## Installation & Requirements

- **Python**: >= 3.11 (tested on 3.13)
- **Dependencies**: none (stdlib only)

```bash
pip install n8n-cli
```

Verify:

```bash
n8n-cli --help
```

See `pyproject.toml` for full build/dependency details.

## Setup

### Option 1: Environment variables

```bash
export N8N_API_URL="https://your-n8n.example.com"
export N8N_API_KEY="your-api-key"
```

> **Security note:** Exporting `N8N_API_KEY` directly will save the key in
> your shell history. Prefer the config file approach with `api_key_command`
> (Option 2 below), or prefix the command with a space (requires
> `HISTCONTROL=ignorespace` in bash) to keep it out of history.

### Option 2: Config file

Create `~/.config/n8n-cli/config.json`:

```json
{
  "api_url": "https://your-n8n.example.com",
  "api_key_command": "rbw get n8n-api-key"
}
```

| Field             | Description                                   |
| ----------------- | --------------------------------------------- |
| `api_url`         | n8n instance URL                              |
| `api_key`         | API key (direct, less secure)                 |
| `api_key_command` | Shell command to retrieve API key (preferred) |
| `api_url_command` | Shell command to retrieve API URL             |
| `timeout`         | Request timeout in seconds (default: 30)      |

Priority: environment variables > `*_command` > direct values.

## Usage

Default output is LLM-friendly text. Add `-j`/`--json` for JSON.

### Credentials

```bash
n8n-cli credential list
n8n-cli credential get <id>
n8n-cli credential create cred.json
n8n-cli credential update <id> updated.json
n8n-cli credential delete <id>
n8n-cli credential test <id>
n8n-cli credential schema httpBasicAuth
```

### Workflows (full JSON round-trip)

```bash
n8n-cli workflow get <id> > workflow.json
n8n-cli workflow update <id> workflow.json   # strips id/tags/shared/pinData
n8n-cli workflow activate <id>
n8n-cli workflow deactivate <id>
```

### Executions

```bash
n8n-cli execution get <id>
n8n-cli execution list --workflow <id> --status error --limit 5
```

### Data Tables

```bash
n8n-cli datatable list
n8n-cli datatable get <id>
n8n-cli datatable create table.json
n8n-cli datatable update <id> new-name
n8n-cli datatable delete <id>
n8n-cli datatable rows <id> --filter '<json>' --sort col:asc --search text --limit 20
n8n-cli datatable insert <id> rows.json --return count|id|all
n8n-cli datatable update-rows <id> body.json
n8n-cli datatable upsert <id> body.json
n8n-cli datatable delete-rows <id> --filter '<json>' [--dry-run]
```

### Raw API

```bash
n8n-cli raw GET /workflows
n8n-cli raw POST /path body.json
n8n-cli raw PUT /path body.json
n8n-cli raw DELETE /path
```
