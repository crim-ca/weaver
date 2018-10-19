STATUS_ACCEPTED = 'accepted'
STATUS_STARTED = 'started'
STATUS_PAUSED = 'paused'
STATUS_SUCCEEDED = 'succeeded'
STATUS_FAILED = 'failed'
STATUS_RUNNING = 'running'
STATUS_FINISHED = 'finished'
STATUS_DISMISSED = 'dismissed'
STATUS_EXCEPTION = 'exception'

job_status_values = frozenset([
    STATUS_ACCEPTED,
    STATUS_STARTED,
    STATUS_PAUSED,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_DISMISSED,
    STATUS_EXCEPTION
])

job_status_categories = {
    # note: only [Succeeded, Failed, Accepted, Running] are OGC compliant
    # note: PyWPS use [Succeeded, Failed, Accepted, Started, Paused, Exception]
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17
    STATUS_RUNNING: frozenset([STATUS_ACCEPTED, STATUS_PAUSED, STATUS_STARTED]),
    STATUS_FINISHED: frozenset([STATUS_SUCCEEDED, STATUS_FAILED, STATUS_DISMISSED, STATUS_EXCEPTION]),
}
