# kagi-search

CLI tool for searching Kagi using session tokens. Scrapes the HTML interface to
avoid using API credits.

## Configuration

Create `~/.config/kagi/config.json`:

```json
{
  "password_command": "rbw get kagi-session-link",
  "timeout": 30,
  "max_retries": 5
}
```

## Getting Your Token

1. Log in to [Kagi](https://kagi.com)
2. Go to [Settings → Session Link](https://kagi.com/settings?p=api)
3. Generate and copy session link
4. Store in password manager

## Usage

See [skills/kagi-search/SKILL.md](../skills/kagi-search/SKILL.md) for usage
examples.

## License

MIT
