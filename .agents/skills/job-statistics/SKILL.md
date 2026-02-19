---
name: job-statistics
description: Retrieve execution statistics for a job including resource usage (CPU, memory), execution duration, data transfer metrics, and performance indicators. Use for monitoring resource consumption and optimizing process configurations.
license: Apache-2.0
compatibility: Requires Weaver API access with statistics feature enabled.
metadata:
  category: job-monitoring
  version: "1.0.0"
  api_endpoint: GET /jobs/{job_id}/statistics
  cli_command: weaver statistics
  author: CRIM
allowed-tools: http_request
---

# Get Job Statistics

Retrieve execution statistics and resource usage for a job.

## When to Use

- Monitoring resource consumption
- Optimizing process configurations
- Capacity planning and resource allocation
- Performance analysis and benchmarking
- Identifying resource bottlenecks
- Cost estimation for cloud resources

## Parameters

### Required

- **job\_id** (string): Job identifier

## CLI Usage

```bash
# Get job statistics
weaver statistics -u $WEAVER_URL -j a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Compare statistics for multiple jobs
for job in $(weaver jobs -u $WEAVER_URL -p my-process -f json | jq -r '.jobs[].jobID'); do
    echo "Job $job:"
    weaver statistics -u $WEAVER_URL -j $job
done
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get statistics
stats = client.statistics(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

print(f"Duration: {stats.body.get('duration')}")
print(f"CPU Usage: {stats.body.get('cpuUsage')}")
print(f"Memory Usage: {stats.body.get('memoryUsage')}")
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/statistics"
```

## Returns

```json
{
  "jobID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "duration": "PT5M32S",
  "executionDuration": "PT5M15S",
  "queueDuration": "PT17S",
  "resource": {
    "cpuUsage": {
      "average": "45%",
      "peak": "87%"
    },
    "memoryUsage": {
      "average": "2.3 GB",
      "peak": "4.1 GB"
    },
    "diskIO": {
      "read": "150 MB",
      "write": "75 MB"
    }
  },
  "dataTransfer": {
    "inputSize": "500 MB",
    "outputSize": "200 MB"
  }
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Statistics Fields

### Timing

- **duration**: Total time from submission to completion
- **executionDuration**: Actual processing time
- **queueDuration**: Time spent waiting in queue

### Resource Usage

- **cpuUsage**: CPU utilization (average and peak)
- **memoryUsage**: RAM consumption (average and peak)
- **diskIO**: Disk read/write operations
- **networkIO**: Network transfer (if applicable)

### Data Metrics

- **inputSize**: Total size of input data
- **outputSize**: Total size of output data
- **transferredData**: Data transferred between services

## Use Cases

### Resource Optimization

```python
# Analyze resource usage patterns
stats = client.statistics(job_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

if stats.body["resource"]["memoryUsage"]["peak"] > "8 GB":
    print("Consider increasing memory allocation")
```

### Cost Estimation

```python
# Calculate approximate cloud compute costs
duration_minutes = parse_duration(stats.body["duration"])
cpu_hours = duration_minutes / 60
estimated_cost = cpu_hours * cost_per_cpu_hour
```

## Related Skills

- [job-status](../job-status/) - Check job status
- [job-logs](../job-logs/) - View execution logs
- [job-monitor](../job-monitor/) - Monitor execution
- [job-list](../job-list/) - Compare multiple jobs

## Documentation

- [Job Statistics](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Resource Management](https://pavics-weaver.readthedocs.io/en/latest/configuration.html#resource-management)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
