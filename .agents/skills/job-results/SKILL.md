---
name: job-results
description: |
  Retrieve output results from a successfully completed job. Downloads output files or retrieves
  inline values. Use when a job has status 'succeeded' and you need to access the outputs.
license: Apache-2.0
compatibility: Requires Weaver API access. Job must have succeeded status.
metadata:
---
# Get Job Results

Retrieve output results from a successfully completed job.

## When to Use

- Getting outputs after job completion
- Downloading result files locally
- Retrieving literal output values
- Accessing workflow step outputs

## Parameters

### Required

- **job\_id** (string): Job identifier

### Optional

- **output\_dir** (path): Directory to download output files
- **download** (boolean): Whether to download files locally

## CLI Usage

```bash
# View results (URLs)
weaver results -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Download to directory
weaver results -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890 -oD ./outputs

# Complete workflow: execute, monitor, get results
weaver execute -u $WEAVER_URL -p my-process -I inputs.json
weaver monitor -u $WEAVER_URL -j <job-id>
weaver results -u $WEAVER_URL -j <job-id> -oD ./outputs
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get results
results = client.results(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

for output_name, output_value in results.body.items():
    if isinstance(output_value, dict) and "href" in output_value:
        print(f"{output_name}: {output_value['href']}")
    else:
        print(f"{output_name}: {output_value}")
```

## Returns

Result format depends on output type:

### File Outputs (Reference Mode)

```json
{
  "output1": {
    "href": "https://weaver.example.com/outputs/job-id/output1.nc",
    "type": "application/netcdf"
  }
}
```

### Literal Outputs (Value Mode)

```json
{
  "count": 42,
  "message": "Processing complete",
  "success": true
}
```

## Error Handling

- **404 Not Found**: Job does not exist
- **400 Bad Request**: Job not yet completed or failed

## Related Skills

- [job-execute](../job-execute/) - Start the job
- [job-monitor](../job-monitor/) - Wait for completion
- [job-status](../job-status/) - Check status

## Documentation

- [Job Results](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
