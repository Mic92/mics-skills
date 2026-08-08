---
name: queue
description: Run long commands in the background without tool timeouts. Use for anything that may run longer than 10 seconds (builds, test suites, deploys)
---

The command is read from stdin:

```bash
queue run <<'EOF'
nix build .#package --no-link -L
EOF
```

`task=<id>` is printed first.
Output streams until the command finishes and the exit code is the command's exit code.
Queues detach after ~100s queue with exit code 75.
The task keeps running.

```bash
queue wait <id>            # re-attach; replays output from the start
queue wait                 # barrier: wait for all my tasks
queue log <id>             # full output so far + status, works while running
queue status [--all]       # my tasks (--all: everyone's); --json for scripts
queue ps <id>              # pid, RSS, CPU of the task's process tree
queue restart <id>         # rerun a failed task without retyping the command
queue kill <id>
queue run [--after ID] [--tail-ok N] [-C DIR]
                           # dependency; tail output on success; working dir
```

Rules:

- Exit code 75 always means a detached build.
- Never pipe the queued command through head/tail. Use `queue log` or `--tail-ok` instead, otherwise output is lost forever.
