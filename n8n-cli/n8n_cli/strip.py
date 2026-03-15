"""Strip read-only fields before sending to n8n API.

The n8n REST API returns metadata fields (timestamps, ownership, etc.)
in GET responses that its PUT/PATCH endpoints reject.  These helpers
remove them so a get→edit→update round-trip works cleanly.
"""

from typing import Any

# Fields common to every resource type.
_COMMON_READONLY: frozenset[str] = frozenset(
    {
        "id",
        "createdAt",
        "updatedAt",
        "homeProject",
        "sharedWithProjects",
        "scopes",
    }
)

# Extra read-only fields per resource kind.
_WORKFLOW_EXTRA: frozenset[str] = frozenset(
    {
        "tags",
        "shared",
        "pinData",
        "isArchived",
        "usedCredentials",
    }
)

_CREDENTIAL_EXTRA: frozenset[str] = frozenset(
    {
        "isManaged",
        "ownedBy",
    }
)

WORKFLOW_READONLY: frozenset[str] = _COMMON_READONLY | _WORKFLOW_EXTRA
CREDENTIAL_READONLY: frozenset[str] = _COMMON_READONLY | _CREDENTIAL_EXTRA


def strip_readonly(data: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    """Return a shallow copy of *data* with *keys* removed."""
    return {k: v for k, v in data.items() if k not in keys}
