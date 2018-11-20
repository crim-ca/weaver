OGC_COMPLIANT = 'OGC_COMPLIANT'

STATUS_ACCEPTED = 'accepted'
STATUS_STARTED = 'started'
STATUS_PAUSED = 'paused'
STATUS_SUCCEEDED = 'succeeded'
STATUS_FAILED = 'failed'
STATUS_RUNNING = 'running'
STATUS_FINISHED = 'finished'
STATUS_DISMISSED = 'dismissed'
STATUS_EXCEPTION = 'exception'
STATUS_PENDING = 'pending'
STATUS_UNKNOWN = 'unknown'  # don't include in any below collections

job_status_values = frozenset([
    STATUS_ACCEPTED,
    STATUS_STARTED,
    STATUS_PAUSED,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_DISMISSED,
    STATUS_EXCEPTION,
    STATUS_PENDING,
])

job_status_categories = {
    # note: only [Succeeded, Failed, Accepted, Running] are OGC compliant
    # note: PyWPS use [Succeeded, Failed, Accepted, Started, Paused, Exception]
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17
    OGC_COMPLIANT: frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED]),
    STATUS_RUNNING: frozenset([STATUS_ACCEPTED, STATUS_PAUSED, STATUS_STARTED]),
    STATUS_FINISHED: frozenset([STATUS_SUCCEEDED, STATUS_FAILED, STATUS_DISMISSED, STATUS_EXCEPTION]),
}


def map_status(wps_execution_status):
    job_status = wps_execution_status.lower().replace('process', '')
    if job_status == STATUS_RUNNING:    # OGC official status but not supported by PyWPS. See twitcher/status.py
        job_status = STATUS_STARTED     # This is the status used by PyWPS
    if job_status in job_status_values:
        return job_status
    return STATUS_UNKNOWN
