---
name: provider-unregister
description: Remove a registered remote provider from Weaver. This disconnects the external service but does not affect the remote service itself. Use when decommissioning integrations or removing outdated provider registrations.
license: Apache-2.0
compatibility: Requires Weaver API access with provider management permissions.
metadata:
  category: provider-management
  version: "1.0.0"
  api_endpoint: DELETE /providers/{provider_id}
  cli_command: weaver unregister
  author: CRIM
allowed-tools: http_request
---

# Unregister Provider

Remove a registered remote provider from Weaver.

## When to Use

- Removing outdated provider registrations
- Decommissioning service integrations
- Cleaning up unused providers
- Updating provider configurations (unregister then re-register)
- Managing provider lifecycle

## Parameters

### Required

- **provider\_id** (string): Provider identifier to remove

## CLI Usage

```bash
# Unregister provider
weaver unregister -u $WEAVER_URL -n my-provider

# List providers before removal
weaver capabilities -u $WEAVER_URL --providers
weaver unregister -u $WEAVER_URL -n old-provider

# Verify removal
weaver capabilities -u $WEAVER_URL --providers
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Unregister provider
result = client.unregister(provider_id="my-provider")

if result.success:
    print("Provider unregistered successfully")
```

## API Request

```bash
curl -X DELETE \
  "${WEAVER_URL}/providers/my-provider"
```

## Returns

```json
{
  "id": "my-provider",
  "status": "unregistered",
  "message": "Provider successfully removed"
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Behavior

- **Does NOT affect**: The remote service (remains operational)
- **Removes**: Provider registration from Weaver
- **Invalidates**: References to provider processes in workflows
- **Preserves**: Historical job records that used the provider

## Impact on Existing Jobs

- **Completed jobs**: Remain accessible with full history
- **Running jobs**: Continue execution (already dispatched)
- **Pending jobs**: May fail if they reference the provider

## Use Cases

### Provider Update

```bash
# Update provider URL or configuration
weaver unregister -u $WEAVER_URL -n my-provider
weaver register -u $WEAVER_URL -n my-provider -w https://new-url.example.com/wps
```

### Cleanup

```python
# Remove unused providers
providers = client.capabilities(providers=True)

for provider in providers.body.get("providers", []):
    # Check if provider is still reachable
    try:
        processes = client.capabilities(provider=provider["id"])
        if not processes.body.get("processes"):
            client.unregister(provider_id=provider["id"])
    except Exception:
        client.unregister(provider_id=provider["id"])
```

### Service Migration

```bash
# Migrate from old to new provider
weaver register -u $WEAVER_URL -n new-provider -w https://new.example.com/wps

# Test new provider
weaver capabilities -u $WEAVER_URL -P new-provider

# Remove old provider
weaver unregister -u $WEAVER_URL -n old-provider
```

## Error Handling

- **404 Not Found**: Provider does not exist
- **403 Forbidden**: Insufficient permissions
- **409 Conflict**: Provider has active jobs

## Related Skills

- [provider-register](../provider-register/) - Register new provider
- [provider-list](../provider-list/) - View all providers
- [job-execute](../job-execute/) - Use provider processes
- [job-list](../job-list/) - Check for provider jobs before removal

## Documentation

- [Provider Management](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
