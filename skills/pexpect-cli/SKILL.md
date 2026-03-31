---
name: pexpect-cli
description: Persistent pexpect sessions. Use when automating interactive terminal programs (ssh, databases, debuggers, REPLs).
---

Each session is a long-lived Python namespace: **all** variables, imports, and functions persist across calls.
Exceptions return exit 1 but the session stays alive. Expression results are not echoed; use `print()`.

```bash
pexpect-cli --start [--name label]   # → prints session id
pexpect-cli --list
pexpect-cli --stop <id>              # also kills spawned children

session=$(pexpect-cli --start --name ssh)
pexpect-cli $session <<'EOF'
child = pexpect.spawn('ssh user@host', encoding='utf-8')  # encoding → .before is str not bytes
child.expect('password:', timeout=30)
child.sendline('secret')
child.expect(r'\$')
EOF

# child still alive next call
pexpect-cli $session <<'EOF'
child.sendline('uptime')
child.expect(r'\$')
print(child.before)
EOF
```

Only stdout is returned. stderr and full history go to `pueue log` (find task id via `pueue status --group pexpect`).

Always set `timeout=` on `expect()`. Catch `pexpect.TIMEOUT` / `pexpect.EOF` for robustness.
