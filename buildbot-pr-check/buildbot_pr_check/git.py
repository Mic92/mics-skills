"""Git helpers (current-branch PR auto-detection via `gh`)."""

import json
import subprocess


def get_current_branch_pr_url() -> str | None:
    """Return the PR URL for the current branch via `gh pr view`, or None."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        if not branch:
            return None

        result = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "url"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                url = data.get("url")
                return url if isinstance(url, str) else None
            except json.JSONDecodeError:
                pass
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None
