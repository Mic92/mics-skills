# context7-cli

CLI tool for fetching up-to-date library documentation from
[Context7](https://context7.com). Get code examples and docs directly into your
LLM prompts.

## Configuration

Create `~/.config/context7/config.json`:

```json
{
  "password_command": "rbw get context7-api-key"
}
```

Or with a direct API key (less secure):

```json
{
  "api_key": "ctx7sk_..."
}
```

## Getting Your API Key

1. Go to [Context7 Dashboard](https://context7.com/dashboard)
2. Generate a free API key
3. Store in your password manager

API keys are optional but recommended for higher rate limits.

## Usage

See [skills/context7-cli/SKILL.md](../skills/context7-cli/SKILL.md) for usage
examples.

## License

MIT
