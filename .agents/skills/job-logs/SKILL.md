---
name: job-logs
description: |
  Retrieve execution logs for debugging and monitoring job execution. Includes process execution
  steps, standard output/error, and timestamps. Use when debugging failed jobs or tracking execution
  details.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
---
# Get Job Logs

Retrieve execution logs for debugging and monitoring.

## When to Use

- Debugging failed jobs
- Understanding execution flow
- Tracking progress in detail
- Identifying errors and warnings

## Parameters

### Required

- **job\_id** (string): Job identifier

## CLI Usage

```bash
weaver logs -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")
logs = client.logs(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

for log_entry in logs.body.get("logs", []):
    print(log_entry)
```

## Returns

Execution logs including:

- Process execution steps
- Standard output/error streams
- Timestamps for each step
- Error messages and stack traces
- Resource usage information

## Related Skills

- [job-status](../job-status/) - Check status
- [job-exceptions](../job-exceptions/) - Get error details

## Documentation

- [Job Logs](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
