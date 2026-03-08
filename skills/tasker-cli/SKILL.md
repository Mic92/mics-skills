---
name: tasker-cli
description: Deploy and trigger Tasker tasks on Android. Use for automating Android via Tasker WebUI and adb.
---

# Usage

## First-time setup

```bash
# On phone: Tasker → Preferences → UI → enable "Use Tasker 2025 UI (VERY EARLY)"
# Open any task for editing, tap ⋮ → WebUI
export TASKER_HOST=192.168.1.100
tasker-cli sync-specs
```

## Deploy a task

```bash
tasker-cli deploy task.json --replace   # clear + deploy
tasker-cli deploy task.json --append    # append to existing
tasker-cli deploy task.json --dry-run   # validate only
cat task.json | tasker-cli deploy -     # from stdin
```

## Task definition format

```json
{
  "actions": [
    {
      "action": "Variable Set",
      "args": { "Name": "%url", "To": "https://api.example.com/data" }
    },
    {
      "action": "HTTP Request",
      "args": { "Method": "0", "URL": "%url", "Timeout (Seconds)": "30" }
    },
    { "action": "Flash", "args": { "Text": "Result: %HTTPD" } }
  ]
}
```

Rules:

- Use human-readable action and arg names (from `tasker-cli specs`)
- All arg values must be strings (booleans: `"true"`/`"false"`)
- Use `tasker-cli specs --search <term>` to find action names and required args

## Conditions and control flow

Conditions use `{"e": <lhs>, "b": <operator>, "f": <rhs>}`. Multiple
conditions on one action are ANDed.

Operators: `Equals`, `NotEqualsString`, `LessThan`, `GreaterThan`, `Matches`,
`IsSet`, `Isn'tSet`

```json
{"action": "Flash", "args": {"Text": "Low!"}, "condition": [{"e": "%BATT", "b": "LessThan", "f": "20"}]}
{"action": "Stop", "args": {"With Error": "false"}, "condition": [{"e": "%par2", "b": "Equals", "f": "enter"}, {"e": "%GF", "b": "NotEqualsString", "f": "%par1"}]}
{"action": "If", "args": {}, "condition": [{"e": "%BATT", "b": "LessThan", "f": "20"}]}
{"action": "Else"}
{"action": "End If"}
```

## Other commands

```bash
tasker-cli ping                       # check WebUI connectivity
tasker-cli show                       # show current task actions
tasker-cli specs --search flash       # search action specs
tasker-cli trigger "My Task" --par1 "value"
```

## Environment variables

- `TASKER_HOST` — phone IP (required, or use --host)
- `TASKER_WEBUI_PORT` — WebUI port (default: 8745)
- `TASKER_ADB_PORT` — adb port (default: auto-detect)
