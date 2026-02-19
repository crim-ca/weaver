---
name: process-list
description: List all available processes with optional filtering by visibility or provider. Retrieve process summaries for discovery. Use when you need to find available processing capabilities or explore what Weaver can do.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: process-management
  version: "1.0.0"
  api_endpoint: GET /processes
  cli_command: weaver capabilities
  author: CRIM
allowed-tools: http_request
---

# List Processes

List all available processes with optional filtering and pagination.

## When to Use

- Discovering available processes
- Finding processes by keyword or category
- Checking deployed processes
- Exploring remote provider capabilities

## Parameters

### Optional

- **provider** (string): Filter by provider ID
- **visibility** (string): Filter by visibility ("public", "private")
- **limit** (integer): Maximum number of results
- **page** (integer): Pagination offset
- **sort** (string): Sort order for results
- **detail** (boolean): Include detailed descriptions

## CLI Usage

```bash
# List all processes
weaver capabilities -u $WEAVER_URL

# List from specific provider
weaver capabilities -u $WEAVER_URL -P my-provider

# List with details
weaver capabilities -u $WEAVER_URL --detail
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# List all
result = client.capabilities()

for process in result.body.get("processes", []):
    print(f"{process['id']}: {process.get('title', process['id'])}")
```

## Returns

```json
{
  "processes": [
    {
      "id": "process-1",
      "title": "Process 1",
      "description": "Brief description",
      "version": "1.0.0"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Related Skills

- [process-describe](../process-describe/) - Get process details
- [process-deploy](../process-deploy/) - Add new process
- [job-execute](../job-execute/) - Run a process as a job with inputs

## Documentation

- [Process Listing](https://pavics-weaver.readthedocs.io/en/latest/processes.html#listing)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html#capabilities)
