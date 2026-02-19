---
name: job-inputs
description: Retrieve the input specifications and values that were provided when a job was executed. Shows what parameters were used to run the process. Use for debugging, reproducing results, or auditing job submissions.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: job-monitoring
  version: "1.0.0"
  api_endpoint: GET /jobs/{job_id}/inputs
  cli_command: weaver inputs
  author: CRIM
allowed-tools: http_request
---

# Get Job Inputs

Retrieve the input values that were provided when a job was executed.

## When to Use

- Reviewing parameters used for a job
- Reproducing job execution with same inputs
- Debugging parameter-related issues
- Auditing job submissions
- Documenting workflow configurations
- Comparing inputs across multiple job runs

## Parameters

### Required
- **job_id** (string): Job identifier

## CLI Usage

```bash
# Get job inputs
weaver inputs -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Save inputs for reuse
weaver inputs -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890 > inputs-to-reuse.json

# Resubmit with same inputs
weaver execute -u $WEAVER_URL -p my-process -I inputs-to-reuse.json
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get inputs
inputs = client.inputs(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

for input_name, input_value in inputs.body.items():
    print(f"{input_name}: {input_value}")

# Reuse inputs for another job
new_job = client.execute(
    process_id="my-process",
    inputs=inputs.body
)
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/inputs"
```

## Returns

```json
{
  "input1": "value1",
  "input2": {
    "href": "https://example.com/input-file.nc",
    "type": "application/netcdf"
  },
  "threshold": 0.5,
  "enabled": true
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Input Types

### Literal Values
```json
{
  "parameter": "string value",
  "count": 42,
  "enabled": true
}
```

### File References
```json
{
  "input_file": {
    "href": "https://example.com/data.tif",
    "type": "image/tiff"
  }
}
```

### Arrays
```json
{
  "files": [
    {"href": "https://example.com/file1.nc"},
    {"href": "https://example.com/file2.nc"}
  ]
}
```

### Vault References
```json
{
  "credentials": {
    "href": "vault://secret-token"
  }
}
```

## Use Cases

### Reproduce Results
```bash
# Get inputs from successful job
weaver inputs -u $WEAVER_URL -j c3d4e5f6-a7b8-9012-cdef-123456789012 > good-inputs.json

# Run again with same parameters
weaver execute -u $WEAVER_URL -p my-process -I good-inputs.json
```

### Debug Failed Jobs
```python
# Compare inputs between successful and failed jobs
success_inputs = client.inputs(job_id="success-job-id")
failed_inputs = client.inputs(job_id="d4e5f6a7-b8c9-0123-def1-234567890123")

# Find differences
for key in success_inputs.body:
    if success_inputs.body[key] != failed_inputs.body.get(key):
        print(f"Different value for {key}")
```

### Audit Trail
```bash
# Document what inputs were used
weaver inputs -u $WEAVER_URL -j $JOB_ID | tee audit/job-$JOB_ID-inputs.json
```

## Related Skills

- [job-execute](../job-execute/) - Submit jobs with inputs
- [job-results](../job-results/) - Get corresponding outputs
- [job-status](../job-status/) - Check job status
- [process-describe](../process-describe/) - See required/optional inputs

## Documentation

- [Job Inputs](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Input Formats](https://pavics-weaver.readthedocs.io/en/latest/processes.html#inputs-outputs)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
