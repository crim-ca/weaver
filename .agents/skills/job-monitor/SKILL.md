---
name: job-monitor
description: Continuously monitor a job until completion or timeout. Polls job status at regular intervals and provides progress updates. Use when you need to wait for a job to complete and get final results.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: job-monitoring
  version: "1.0.0"
  cli_command: weaver monitor
  author: CRIM
allowed-tools: http_request
---

# Monitor Job

Continuously monitor a job until completion or timeout with regular status polling.

## When to Use

- Waiting for an asynchronous job to complete
- Tracking long-running workflow execution
- Getting real-time progress updates
- Automatically retrieving results when done

## Parameters

### Required
- **job_id** (string): Job identifier to monitor

### Optional
- **timeout** (integer): Maximum time to wait in seconds (default: 60)
- **interval** (integer): Polling interval in seconds (default: 5)

## CLI Usage

```bash
# Monitor with defaults
weaver monitor -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Custom timeout and interval
weaver monitor -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890 -tS 300 -tI 10

# Execute and monitor in one command
weaver execute -u $WEAVER_URL -p my-process -I inputs.json -M
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Start monitoring
status = client.monitor(
    job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    timeout=300,
    interval=10
)

print(f"Final status: {status.body['status']}")
```

## Returns

- **status**: Final job status (succeeded, failed, dismissed)
- **progress**: Progress percentage (0-100)
- **duration**: Total execution time
- **message**: Status message or error details

## Documentation

- [Job Monitoring](https://pavics-weaver.readthedocs.io/en/latest/processes.htmling-a-job-execution-getstatus)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
