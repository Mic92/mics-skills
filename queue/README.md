# queue

Agent-friendly frontend for [pueue](https://github.com/Nukesor/pueue).

Pueue is a nice frontend for humans to follow up on the status of background commands.
However I noticed that agent always struggled to use it correctly.

## My observations

- pueue list jobs from multiple agent session, which is unnecessary confusing for the current agent session
- `pueue add` has quoting issues when passing commands
- `pueue log` limits the number of lines by default but agents tend to already use tail anyway.
- agents have to always use ids, also in most cases its enough to just refer to the last spawned command.

## Instead queue does the following

Agents pass commands via stdin

```bash
queue run <<'EOF'
cd ~/git/nixpkgs
nix build -f . hello --no-link -L
EOF
```

The first line for queue is the task id `task=<id>`.
It will also block on the command and stream the output right away all in just one command.
Furthermore the run command has a default timeout of 100s, after which it is detached
with a message on how to inspect the command.

## Subcommands

```bash
queue run [--timeout SECS] [--detach] [--after ID...] [-C DIR] [--name NAME] [--tail-ok N]
queue wait [ID...]        # re-attach; without ids: barrier over all own tasks
queue log [ID] [--lines N]  # full log + status header; works while running
queue status [--all] [--json]
queue restart ID          # rerun with the stored command, no re-quoting
queue kill ID
queue ps ID [--json]      # pid, RSS and CPU time of the task's process tree
```

## Install

```bash
nix run github:Mic92/mics-skills#queue -- status
```

Or add `mics-skills.packages.${system}.queue` to your home-manager
packages. `pueued` does not need to be running; queue starts it on demand.
