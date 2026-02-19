---
name: job-exceptions
description: |
  Retrieve detailed exception and error information for failed jobs including error messages, stack
  traces, and debugging information. Use when diagnosing job failures or troubleshooting process
  execution issues.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
---
# Get Job Exceptions

Retrieve detailed exception and error information for failed jobs.

## When to Use

- Diagnosing why a job failed
- Getting detailed error messages
- Debugging process execution issues
- Reporting bugs or issues
- Understanding failure causes

## Parameters

### Required

- **job\_id** (string): Job identifier

## CLI Usage

```bash
# Get exceptions for a failed job
weaver exceptions -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Combine with logs for full context
weaver logs -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890
weaver exceptions -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get exceptions
exceptions = client.exceptions(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

for exception in exceptions.body.get("exceptions", []):
    print(f"Error: {exception.get('Text', 'Unknown error')}")
    print(f"Code: {exception.get('Code', 'N/A')}")
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/exceptions"
```

## Returns

```json
{
  "exceptions": [
    {
      "Code": "InvalidParameterValue",
      "Text": "Input parameter 'threshold' must be between 0 and 1, got 1.5",
      "Locator": "threshold"
    }
  ]
}
```

**Note**: Response may include additional fields. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Exception Information

Typical exception fields:

- **Code**: Error code (e.g., InvalidParameterValue, ProcessFailed)
- **Text**: Human-readable error message
- **Locator**: Which parameter or component caused the error
- **StackTrace**: Detailed stack trace (if available)

## Common Error Codes

- **InvalidParameterValue**: Invalid input parameter
- **MissingParameterValue**: Required parameter not provided
- **ProcessFailed**: Process execution failed
- **NoApplicableCode**: Generic error
- **StorageQuotaExceeded**: Insufficient storage space
- **NetworkError**: Network connectivity issues

## Related Skills

- [job-logs](../job-logs/) - View execution logs
- [job-status](../job-status/) - Check job status
- [job-execute](../job-execute/) - Retry with corrected parameters
- [process-describe](../process-describe/) - Validate input requirements

## Documentation

- [Job Exceptions](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Error Handling](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
