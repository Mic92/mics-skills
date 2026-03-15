"""Filter request bodies to only include fields the n8n public API accepts.

The n8n public API validates requests against its OpenAPI spec using
express-openapi-validator.  The workflow schema sets
``additionalProperties: false``, so any field not in the spec is
rejected with "request/body must NOT have additional properties".

Rather than maintaining a denylist of read-only fields, we allowlist
exactly the fields each endpoint accepts — derived from the OpenAPI
YAML definitions in the n8n source tree:

  packages/cli/src/public-api/v1/handlers/workflows/spec/schemas/workflow.yml
  packages/cli/src/public-api/v1/handlers/credentials/spec/schemas/update-credential-request.yml
"""

from typing import Any

# PUT /workflows/{id}  — workflow.yml, additionalProperties: false
# We exclude fields marked readOnly in the spec:
#   id, active, createdAt, updatedAt, tags  — top-level readOnly
#   shared      — contains nested readOnly fields (project.id, project.type)
#   activeVersion — entire object is readOnly
WORKFLOW_WRITABLE: frozenset[str] = frozenset(
    {
        "name",
        "nodes",
        "connections",
        "settings",
        "staticData",
    }
)

# PATCH /credentials/{id}  — update-credential-request.yml
# No additionalProperties constraint, but we filter anyway to avoid
# sending back metadata (timestamps, ownership, scopes, etc.) that
# the endpoint ignores or that could break in future API versions.
CREDENTIAL_WRITABLE: frozenset[str] = frozenset(
    {
        "name",
        "type",
        "data",
        "isGlobal",
        "isResolvable",
        "isPartialData",
    }
)


def keep_writable(data: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    """Return a shallow copy of *data* keeping only *keys*."""
    return {k: v for k, v in data.items() if k in keys}
