# tasker-cli

CLI tool to deploy and trigger [Tasker](https://tasker.joaoapps.com/) tasks on
Android via the WebUI API and adb broadcast.

## Setup

### Enable the WebUI on your phone

1. Open **Tasker** → **Preferences** (⋮ menu) → **UI**
2. Enable **Use Tasker 2025 UI (VERY EARLY)** (required for WebUI support)
3. Go back and open any **Task** for editing
4. Tap the **⋮ menu** → **WebUI**
5. The WebUI server starts and shows the phone's IP and port (default 8745)

The phone and your computer must be on the same network.

### Connect and sync specs

```bash
export TASKER_HOST=192.168.1.100  # your phone's IP
tasker-cli sync-specs             # fetch action definitions from the phone
```

## Usage

```bash
tasker-cli deploy task.json --replace
tasker-cli show
tasker-cli trigger "My Task" --par1 "value"
tasker-cli specs --search flash
```

See `skills/tasker-cli/SKILL.md` for the full task definition format.
