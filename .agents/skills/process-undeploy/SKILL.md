---
name: process-undeploy
description: Remove a deployed process from Weaver. This action is irreversible and will delete the process definition. Use when you need to clean up unused processes or remove deprecated process versions.
license: Apache-2.0
compatibility: Requires Weaver API access with process management permissions.
metadata:
  category: process-management
  version: "1.0.0"
  api_endpoint: DELETE /processes/{process_id}
  cli_command: weaver undeploy
  author: CRIM
allowed-tools: http_request
---

# Undeploy Process

Remove a deployed process from Weaver permanently.

## When to Use

- Removing unused or deprecated processes
- Cleaning up test processes
- Decommissioning old process versions
- Managing process lifecycle

## Parameters

### Required

- **process\_id** (string): Process identifier to remove

### Optional

- **provider** (string): Provider identifier for remote processes

## CLI Usage

```bash
# Undeploy local process
weaver undeploy -u $WEAVER_URL -p my-process

# Confirm before undeploying
weaver describe -u $WEAVER_URL -p my-process  # Check first
weaver undeploy -u $WEAVER_URL -p my-process
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Undeploy process
result = client.undeploy(process_id="my-process")

if result.success:
    print(f"Process removed successfully")
```

## API Request

```bash
curl -X DELETE \
  "${WEAVER_URL}/processes/my-process"
```

## Returns

- **status**: Confirmation of removal
- **message**: Success or error message

## Error Handling

- **404 Not Found**: Process does not exist
- **403 Forbidden**: Insufficient permissions to undeploy
- **409 Conflict**: Process has active jobs

## Related Skills

- [process-deploy](../process-deploy/) - Deploy new process
- [process-list](../process-list/) - View all processes
- [process-describe](../process-describe/) - Check process details before removal

## Documentation

- [Process Undeployment](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
