# n8n-cli

Python CLI for n8n API operations — stdlib only, no dependencies.

- Credential, workflow, execution, tag, data table CRUD
- Webhook testing, bulk import/apply
- Raw API escape hatch

## Install

```bash
pip install n8n-cli
```

## Setup

### Environment variables

```bash
export N8N_API_URL="https://your-n8n.example.com"
export N8N_API_KEY="your-api-key"
```

### Config file (preferred)

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

See [SKILL.md](../skills/n8n-cli/SKILL.md) for full command reference.

```bash
n8n-cli --help
n8n-cli <command> --help
```

Default output is LLM-friendly text. Add `-j`/`--json` for JSON.
