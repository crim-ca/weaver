---
name: job-list
description: List jobs with optional filtering by process, status, date range, tags, and more. Supports pagination and sorting. Use when you need to find specific jobs, monitor multiple executions, or generate job reports.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: job-management
  version: "1.0.0"
  api_endpoint: GET /jobs
  cli_command: weaver jobs
  author: CRIM
allowed-tools: http_request
---

# List Jobs

List jobs with filtering, pagination, and sorting capabilities.

## When to Use

- Finding jobs by process or status
- Monitoring multiple job executions
- Generating job reports and statistics
- Debugging failed jobs
- Cleaning up old jobs
- Auditing job history

## Parameters

### Optional
- **process** (string): Filter by process ID
- **provider** (string): Filter by provider ID
- **status** (string): Filter by job status (running, succeeded, failed, etc.)
- **limit** (integer): Maximum number of results (default: 10)
- **page** (integer): Page number for pagination (default: 0)
- **sort** (string): Sort order (e.g., "created:desc")
- **tags** (list): Filter by job tags
- **date** (string): Filter by date range
- **detail** (boolean): Include detailed information

## CLI Usage

```bash
# List all jobs
weaver jobs -u $WEAVER_URL

# Filter by process
weaver jobs -u $WEAVER_URL -p my-process

# Filter by status
weaver jobs -u $WEAVER_URL -s succeeded

# Combine filters
weaver jobs -u $WEAVER_URL -p my-process -s failed

# With pagination
weaver jobs -u $WEAVER_URL --limit 50 --page 2

# Sort by creation date
weaver jobs -u $WEAVER_URL --sort created:desc
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# List all jobs
jobs = client.jobs()

for job in jobs.body.get("jobs", []):
    print(f"{job['jobID']}: {job['status']}")

# Filter by process and status
failed_jobs = client.jobs(
    process="my-process",
    status="failed"
)

# Get detailed information
detailed = client.jobs(detail=True, limit=100)
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/jobs?process=my-process&status=succeeded&limit=20&page=0"
```

## Returns

```json
{
  "jobs": [
    {
      "jobID": "12345678-1234-5678-1234-567890abcdef",
      "processID": "my-process",
      "status": "succeeded",
      "created": "2026-02-19T10:00:00Z",
      "finished": "2026-02-19T10:05:00Z",
      "duration": "PT5M"
    }
  ],
  "total": 150,
  "limit": 20,
  "page": 0,
  "links": {
    "next": "/jobs?page=1&limit=20"
  }
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Job Status Values

- **accepted**: Job received and queued
- **running**: Job is currently executing
- **succeeded**: Job completed successfully
- **failed**: Job failed with errors
- **dismissed**: Job was cancelled by user

## Filtering Examples

### By Date Range
```bash
weaver jobs -u $WEAVER_URL --date "2026-02-01/2026-02-19"
```

### By Multiple Statuses
```bash
# Get all active jobs (accepted or running)
weaver jobs -u $WEAVER_URL -s accepted,running
```

### By Tags
```bash
weaver jobs -u $WEAVER_URL --tags production,validated
```

## Related Skills

- [job-status](../job-status/) - Check individual job status
- [job-execute](../job-execute/) - Create new jobs
- [job-dismiss](../job-dismiss/) - Cancel jobs
- [job-results](../job-results/) - Retrieve job outputs

## Documentation

- [Job Management](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Job Filtering](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
