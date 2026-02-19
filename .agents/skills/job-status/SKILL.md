---
name: job-status
description: Check the current execution status of a job including progress, timestamps, and state information. Use when you need to check if a job is still running, has completed, or has failed.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: job-monitoring
  version: "1.0.0"
  api_endpoint: GET /jobs/{job_id}
  cli_command: weaver status
  author: CRIM
allowed-tools: http_request
---

# Get Job Status

Check current execution status of a job with progress and timestamps.

## When to Use

- Checking if a job is complete
- Getting progress percentage
- Determining job state (running, succeeded, failed)
- Debugging failed jobs

## Parameters

### Required

- **job\_id** (string): Job identifier

## CLI Usage

```bash
weaver status -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")
status = client.status(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

print(f"Status: {status.body['status']}")
print(f"Progress: {status.body.get('progress', 0)}%")
```

## Returns

```json
{
  "jobID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "progress": 45,
  "message": "Processing step 2 of 4",
  "created": "2026-02-19T10:00:00Z",
  "started": "2026-02-19T10:00:05Z",
  "processID": "my-process"
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Job Status Values

- **accepted**: Job received and queued
- **running**: Job is executing
- **succeeded**: Job completed successfully
- **failed**: Job failed with errors
- **dismissed**: Job was cancelled

## Related Skills

- [job-monitor](../job-monitor/) - Wait for completion
- [job-logs](../job-logs/) - View execution logs
- [job-results](../job-results/) - Retrieve outputs

## Documentation

- [Job Status](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
