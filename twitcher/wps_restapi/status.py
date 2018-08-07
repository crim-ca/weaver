STATUS_ACCEPTED = 'Accepted'
STATUS_STARTED = 'Started'
STATUS_PAUSED = 'Paused'
STATUS_SUCCEEDED = 'Succeeded'
STATUS_FAILED = 'Failed'
STATUS_RUNNING = 'Running'
STATUS_FINISHED = 'Finished'

status_values = frozenset([
    STATUS_ACCEPTED,
    STATUS_STARTED,
    STATUS_PAUSED,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_FINISHED,
])

status_categories = {
    # note: only [Succeeded, Failed, Accepted, Running] are OGC compliant
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17
    STATUS_RUNNING: frozenset([STATUS_ACCEPTED, STATUS_PAUSED, STATUS_STARTED]),
    STATUS_FINISHED: frozenset([STATUS_SUCCEEDED, STATUS_FAILED]),
}
