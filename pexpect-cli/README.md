# pexpect-cli

A CLI tool for managing persistent pexpect sessions using pueue as the process
manager.

## Features

- **Persistent sessions**: Maintain long-running interactive processes across
  multiple invocations
- **Multiple sessions**: Run multiple pexpect sessions in parallel
- **Built-in monitoring**: Leverage pueue's logging and status tracking
- **Real-time output**: Stream output to pueue logs as commands execute
- **Isolated queue**: All sessions run in a dedicated `pexpect` group
- **Simple interface**: Execute Python code via stdin

## Architecture

- **pexpect-server**: Long-running server managed by pueue that maintains the
  pexpect namespace
- **pexpect-cli**: Client that sends Python code to the server via Unix sockets
- **Session ID**: Unique UUID-based identifiers (not pueue task IDs)
- **Pueue group**: All sessions run in the `pexpect` group for isolation

## Installation

With Nix:

```bash
nix run github:Mic92/mics-skills#pexpect-cli
```

Or add to your NixOS/home-manager configuration.

## Usage

See [skills/pexpect-cli/SKILL.md](../skills/pexpect-cli/SKILL.md) for usage
examples.

## Socket Location

Sockets are stored securely with proper permissions (0o700):

- **Preferred**: `$XDG_RUNTIME_DIR/pexpect-cli/{session_id}.sock`
- **Fallback**: `$XDG_CACHE_HOME/pexpect-cli/sockets/{session_id}.sock`

## Monitoring with Pueue

Since sessions are pueue tasks in the `pexpect` group:

```bash
# View all pexpect sessions
pueue status --group pexpect

# Follow live output
pueue follow <task-id>

# View full logs
pueue log <task-id>

# Kill all pexpect sessions
pueue clean --group pexpect
```

## Troubleshooting

### Session not starting

```bash
# Check pueue daemon is running
pueue status

# If not, start it
pueued -d
```

### Socket not found

```bash
# Check session is actually running
pueue status --group pexpect

# Check socket location
ls -la $XDG_RUNTIME_DIR/pexpect-cli/
```

## License

MIT
