---
name: job-dismiss
description: |
  Cancel a running or pending job. The job status will be updated to "dismissed" and execution will
  be terminated. Use when you need to stop a job that is taking too long, was submitted with
  incorrect parameters, or is no longer needed.
license: Apache-2.0
compatibility: Requires Weaver API access with job management permissions.
metadata:
---
# Dismiss Job

Cancel a running or pending job and mark it as dismissed.

## When to Use

- Stopping a job with incorrect parameters
- Cancelling long-running jobs no longer needed
- Freeing resources from stuck jobs
- Interrupting jobs during testing
- Managing resource allocation

## Parameters

### Required

- **job\_id** (string): Job identifier to cancel

## CLI Usage

```bash
# Dismiss a job
weaver dismiss -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Check status after dismissal
weaver status -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Dismiss job
result = client.dismiss(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

if result.success:
    print("Job dismissed successfully")
    
# Verify status
status = client.status(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")
print(f"Job status: {status.body['status']}")  # Should be "dismissed"
```

## API Request

```bash
curl -X DELETE \
  "${WEAVER_URL}/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

## Returns

```json
{
  "jobID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "dismissed",
  "message": "Job dismissed by user request"
}
```

**Note**: Response may include additional fields. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Behavior

- **Running jobs**: Will be terminated gracefully if possible
- **Pending jobs**: Removed from queue without execution
- **Completed jobs**: Cannot be dismissed (already finished)
- **Failed jobs**: Cannot be dismissed (already terminated)

## Error Handling

- **404 Not Found**: Job does not exist
- **403 Forbidden**: Insufficient permissions
- **410 Gone**: Job already dismissed

## Related Skills

- [job-execute](../job-execute/) - Start a job
- [job-status](../job-status/) - Check job status
- [job-monitor](../job-monitor/) - Monitor execution
- [job-list](../job-list/) - Find jobs to dismiss

## Documentation

- [Job Dismissal](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
