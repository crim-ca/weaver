---
name: process-deploy
description: |
  Deploy a new process or application package to Weaver using CWL (Common Workflow Language)
  definitions. Supports Docker containers, remote WPS references, and workflow definitions. Use when
  you need to add a new processing capability to Weaver.
license: Apache-2.0
compatibility: Requires Weaver API access. Supports CWL v1.0, v1.1, v1.2.
metadata:
---

# Deploy Process

Deploy a new process or application package to Weaver using CWL (Common Workflow Language) definitions.

## When to Use

- Adding a new processing capability to Weaver
- Deploying Docker-based applications
- Registering remote WPS process references
- Creating workflow processes that chain multiple steps

## Parameters

### Required

- **process\_id** (string): Unique identifier for the process (lowercase, hyphens allowed)
- **package** (CWL object or file path): Application package definition
  - Can be CWL YAML/JSON file
  - Can be reference URL to remote process
  - Can be inline CWL document

### Optional

- **visibility** (string): Process visibility ("public" or "private"), default: "public"
- **auth** (auth handler): Authentication for protected endpoints

## CLI Usage

```bash
# Deploy from local CWL file
weaver deploy -u https://weaver.example.com -p my-process -b process.cwl

# Deploy with specific visibility
weaver deploy -u $WEAVER_URL -p my-process -b process.cwl --visibility private
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")
result = client.deploy(
    body="process.cwl",
    process_id="my-process",
    visibility="public"
)

print(f"Deployed: {result.body['id']}")
```

## API Request

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
  "processDescription": {
    "process": {
      "id": "my-process"
    }
  },
  "executionUnit": [{
    "href": "https://example.com/process.cwl"
  }]
}' \
  "${WEAVER_URL}/processes"
```

## Returns

```json
{
  "processSummary": {
    "id": "my-process",
    "version": "1.0.0",
    "title": "My Process",
    "jobControlOptions": ["async-execute", "sync-execute"],
    "outputTransmission": ["value", "reference"],
    "processDescriptionURL": "https://weaver.example.com/processes/my-process"
  },
  "deploymentDone": true
}
```

**Note**: Response may include additional fields such as `links`, `keywords`, and extended `process` details. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Error Handling

- **409 Conflict**: Process with this ID already exists
- **400 Bad Request**: Invalid CWL definition or parameters
- **401 Unauthorized**: Authentication required

## Related Skills

- [process-describe](../process-describe/) - Get process details
- [job-execute](../job-execute/) - Run the deployed process
- [process-undeploy](../process-undeploy/) - Remove the process

## Documentation

- [Process Operations](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CWL Application Packages](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
