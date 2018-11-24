from typing import AnyStr, Optional, Union
# noinspection PyProtectedMember
from pywps.response.status import _WPS_STATUS, WPS_STATUS

STATUS_COMPLIANT_OGC = 'STATUS_COMPLIANT_OGC'
STATUS_COMPLIANT_PYWPS = 'STATUS_COMPLIANT_PYWPS'
STATUS_COMPLIANT_OWSLIB = 'STATUS_COMPLIANT_OWSLIB'
STATUS_CATEGORY_FINISHED = 'STATUS_CATEGORY_FINISHED'
STATUS_CATEGORY_RUNNING = 'STATUS_CATEGORY_RUNNING'
STATUS_CATEGORY_FAILED = 'STATUS_CATEGORY_FAILED'

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
    STATUS_RUNNING,
    STATUS_FINISHED,
    STATUS_DISMISSED,
    STATUS_EXCEPTION,
    STATUS_PENDING,
])

job_status_categories = {
    # note:
    #   OGC compliant:  [Accepted, Running, Succeeded, Failed]
    #   PyWPS uses:     [Accepted, Started, Succeeded, Failed, Paused, Exception]
    #   OWSLib users:   [Accepted, Running, Succeeded, Failed, Paused] (with 'Process' in front)
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17
    STATUS_COMPLIANT_OGC:       frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED]),
    STATUS_COMPLIANT_PYWPS:     frozenset([STATUS_ACCEPTED, STATUS_STARTED, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_PAUSED, STATUS_EXCEPTION]),
    STATUS_COMPLIANT_OWSLIB:    frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_PAUSED]),
    STATUS_CATEGORY_RUNNING:    frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_STARTED, STATUS_PAUSED]),
    STATUS_CATEGORY_FINISHED:   frozenset([STATUS_FAILED, STATUS_DISMISSED, STATUS_EXCEPTION, STATUS_SUCCEEDED, STATUS_FINISHED]),
    STATUS_CATEGORY_FAILED:     frozenset([STATUS_FAILED, STATUS_DISMISSED, STATUS_EXCEPTION])
}


# noinspection PyProtectedMember
STATUS_PYWPS_MAP = {s: _WPS_STATUS._fields[s] for s in range(len(WPS_STATUS))}


def map_status(wps_status, compliant=STATUS_COMPLIANT_OGC):
    # type: (Union[AnyStr, int], Optional[AnyStr]) -> AnyStr
    """
    Maps WPS statuses (twitcher.status, OWSLib or PyWPS) to OWSLib/PyWPS compatible values.
    For each compliant combination, unsupported statuses are changed to corresponding ones (with closest logical match).
    Statuses are returned with `twitcher.status.job_status_values` format (lowercase and not preceded by 'Process').

    :param wps_status: one of `twitcher.status.job_status_values` to map to `compliant` standard or PyWPS `int` status.
    :param compliant: one of `STATUS_COMPLIANT_[...]` values.
    :returns: mapped status complying to the requested compliant category, or `STATUS_UNKNOWN` if no match found.
    """

    # case of raw PyWPS status
    if isinstance(wps_status, int):
        return map_status(STATUS_PYWPS_MAP[wps_status], compliant)
    job_status = wps_status.lower().replace('process', '')

    if compliant == STATUS_COMPLIANT_OGC:
        if job_status in job_status_categories[STATUS_CATEGORY_RUNNING]:
            if job_status in [STATUS_STARTED, STATUS_PAUSED]:
                job_status = STATUS_RUNNING
        elif job_status in job_status_categories[STATUS_CATEGORY_FINISHED]:
            if job_status in [STATUS_DISMISSED, STATUS_EXCEPTION]:
                job_status = STATUS_FAILED

    elif compliant == STATUS_COMPLIANT_PYWPS:
        if job_status == STATUS_RUNNING:
            job_status = STATUS_STARTED
        elif job_status == STATUS_DISMISSED:
            job_status = STATUS_FAILED

    elif compliant == STATUS_COMPLIANT_OWSLIB:
        if job_status == STATUS_STARTED:
            job_status = STATUS_RUNNING
        elif job_status in job_status_categories[STATUS_CATEGORY_FAILED] and job_status != STATUS_FAILED:
            job_status = STATUS_FAILED

    # special cases applicable to all
    if job_status == STATUS_PENDING:
        job_status = STATUS_ACCEPTED
    if job_status in [STATUS_FINISHED, 'successful']:
        job_status = STATUS_SUCCEEDED

    if job_status in job_status_values:
        return job_status
    return STATUS_UNKNOWN
