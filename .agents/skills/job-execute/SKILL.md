---
name: job-execute
description: |
  Execute a deployed process with specified inputs. Supports synchronous and asynchronous execution
  modes with various output formats. Use when you need to run a process with specific input data and
  retrieve results.
license: Apache-2.0
compatibility: Requires Weaver API access. Supports async/sync execution modes.
metadata:
---

# Execute Process

Execute a deployed process with specified inputs in synchronous or asynchronous mode.

## When to Use

- Running a deployed process with input data
- Starting asynchronous long-running jobs
- Getting immediate results from fast processes (sync mode)
- Executing workflows with multiple steps

## Parameters

### Required

- **process\_id** (string): Process identifier to execute
- **inputs** (object or file): Process input values
  - Can be JSON/YAML file path
  - Can be inline key=value pairs
  - Can be CWL input format

### Optional

- **mode** (string): Execution mode
  - `async`: Asynchronous execution (default) - returns job ID immediately
  - `sync`: Synchronous execution - waits for completion
  - `auto`: Let server decide based on estimated duration
- **response** (string): Response format
  - `document`: Full job status document (default)
  - `raw`: Direct output results
- **output\_transmission** (string): How outputs are returned
  - `reference`: URLs to output files (default)
  - `value`: Inline output values
- **subscribers** (object): Notification callbacks for job events
- **headers** (object): Custom HTTP headers

## CLI Usage

```bash
# Async execution with inputs from file
weaver execute -u $WEAVER_URL -p my-process -I inputs.json

# Sync execution with inline inputs
weaver execute -u $WEAVER_URL -p echo -i message="Hello World" -M sync

# With monitoring
weaver execute -u $WEAVER_URL -p my-process -I inputs.json -M

# Execute and wait for results
JOB_ID=$(weaver execute -u $WEAVER_URL -p my-process -I inputs.json -f json | jq -r .jobID)
weaver monitor -u $WEAVER_URL -j $JOB_ID
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Async execution
result = client.execute(
    process_id="my-process",
    inputs={"input1": "value1", "input2": "value2"},
    mode="async"
)

job_id = result.body["jobID"]
print(f"Job started: {job_id}")

# Sync execution
result = client.execute(
    process_id="echo",
    inputs={"message": "Hello"},
    mode="sync"
)

print(f"Result: {result.body}")
```

## API Request

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Prefer: respond-async" \
  -d '{
  "inputs": {
    "input1": "value1",
    "input2": {"href": "https://example.com/data.txt"}
  },
  "outputs": {
    "output1": {"transmissionMode": "reference"}
  }
}' \
  "${WEAVER_URL}/processes/my-process/execution"
```

## Returns

### For Async Mode

```json
{
  "jobID": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "status": "accepted",
  "location": "https://weaver.example.com/jobs/b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "created": "2026-02-19T10:00:00Z",
  "processID": "my-process"
}
```

**Note**: Response may include additional fields such as `links`, `message`, `progress`, and execution details. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

### For Sync Mode

```json
{
  "outputs": {
    "output1": {
      "href": "https://weaver.example.com/outputs/result.nc",
      "type": "application/netcdf"
    }
  },
  "status": "succeeded",
  "duration": "PT2M30S"
}
```

**Note**: Synchronous responses include complete output data or references. Additional fields may include `logs`,
`statistics`, and `provenance`.

## Input Format Examples

### Literal Values

```json
{
  "inputs": {
    "message": "Hello World",
    "count": 42,
    "enabled": true
  }
}
```

### File References

```json
{
  "inputs": {
    "input_file": {
      "href": "https://example.com/data.nc"
    }
  }
}
```

### Multiple Files (Array)

```json
{
  "inputs": {
    "input_files": [
      {"href": "https://example.com/file1.txt"},
      {"href": "https://example.com/file2.txt"}
    ]
  }
}
```

### Vault References

```json
{
  "inputs": {
    "credentials": {
      "href": "vault://my-secret-token"
    }
  }
}
```

## Error Handling

- **404 Not Found**: Process does not exist
- **400 Bad Request**: Invalid inputs or parameters
- **422 Unprocessable Entity**: Input validation failed
- **503 Service Unavailable**: Execution resources unavailable

## Related Skills

- [job-monitor](../job-monitor/) - Wait for job completion
- [job-status](../job-status/) - Check job status
- [job-results](../job-results/) - Retrieve output results
- [job-dismiss](../job-dismiss/) - Cancel running job

## Documentation

- [Process Execution](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Input/Output Formats](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
