from typing import TYPE_CHECKING

from pywps.response.status import _WPS_STATUS, WPS_STATUS

if TYPE_CHECKING:
    from typing import AnyStr, Union    # noqa: F401
    AnyStatusType = Union[AnyStr, int]  # noqa: F401

STATUS_COMPLIANT_OGC = "STATUS_COMPLIANT_OGC"
STATUS_COMPLIANT_PYWPS = "STATUS_COMPLIANT_PYWPS"
STATUS_COMPLIANT_OWSLIB = "STATUS_COMPLIANT_OWSLIB"
STATUS_CATEGORY_FINISHED = "STATUS_CATEGORY_FINISHED"
STATUS_CATEGORY_RUNNING = "STATUS_CATEGORY_RUNNING"
STATUS_CATEGORY_FAILED = "STATUS_CATEGORY_FAILED"

STATUS_ACCEPTED = "accepted"
STATUS_STARTED = "started"
STATUS_PAUSED = "paused"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_RUNNING = "running"
STATUS_DISMISSED = "dismissed"
STATUS_EXCEPTION = "exception"
STATUS_UNKNOWN = "unknown"  # don't include in any below collections

JOB_STATUS_VALUES = frozenset([
    STATUS_ACCEPTED,
    STATUS_STARTED,
    STATUS_PAUSED,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_DISMISSED,
    STATUS_EXCEPTION,
])

# pylint: disable=C0301,line-too-long
JOB_STATUS_CATEGORIES = {
    # note:
    #   OGC compliant:  [Accepted, Running, Succeeded, Failed]
    #   PyWPS uses:     [Accepted, Started, Succeeded, Failed, Paused, Exception]
    #   OWSLib users:   [Accepted, Running, Succeeded, Failed, Paused] (with 'Process' in front)
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17
    # corresponding statuses are aligned vertically for 'COMPLIANT' groups
    STATUS_COMPLIANT_OGC:       frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED]),                                   # noqa: E241, E501
    STATUS_COMPLIANT_PYWPS:     frozenset([STATUS_ACCEPTED, STATUS_STARTED, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_PAUSED, STATUS_EXCEPTION]),  # noqa: E241, E501
    STATUS_COMPLIANT_OWSLIB:    frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED, STATUS_PAUSED]),                    # noqa: E241, E501
    # utility categories
    STATUS_CATEGORY_RUNNING:    frozenset([STATUS_ACCEPTED, STATUS_RUNNING, STATUS_STARTED,   STATUS_PAUSED]),                                   # noqa: E241, E501
    STATUS_CATEGORY_FINISHED:   frozenset([STATUS_FAILED, STATUS_DISMISSED, STATUS_EXCEPTION, STATUS_SUCCEEDED]),                                # noqa: E241, E501
    STATUS_CATEGORY_FAILED:     frozenset([STATUS_FAILED, STATUS_DISMISSED, STATUS_EXCEPTION]),                                                  # noqa: E241, E501
}

# id -> str
STATUS_PYWPS_MAP = {s: _WPS_STATUS._fields[s].lower() for s in range(len(WPS_STATUS))}
# str -> id
STATUS_PYWPS_IDS = {k.lower(): v for v, k in STATUS_PYWPS_MAP.items()}


def map_status(wps_status, compliant=STATUS_COMPLIANT_OGC):
    # type: (AnyStatusType, AnyStr) -> AnyStr
    """
    Maps WPS statuses (weaver.status, OWSLib or PyWPS) to OWSLib/PyWPS compatible values.
    For each compliant combination, unsupported statuses are changed to corresponding ones (with closest logical match).
    Statuses are returned with `weaver.status.JOB_STATUS_VALUES` format (lowercase and not preceded by 'Process').

    :param wps_status: one of `weaver.status.JOB_STATUS_VALUES` to map to `compliant` standard or PyWPS `int` status.
    :param compliant: one of `STATUS_COMPLIANT_[...]` values.
    :returns: mapped status complying to the requested compliant category, or `STATUS_UNKNOWN` if no match found.
    """

    # case of raw PyWPS status
    if isinstance(wps_status, int):
        return map_status(STATUS_PYWPS_MAP[wps_status], compliant)

    # remove 'Process' from OWSLib statuses and lower for every compliant
    job_status = wps_status.lower().replace("process", "")

    if compliant == STATUS_COMPLIANT_OGC:
        if job_status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_RUNNING]:
            if job_status in [STATUS_STARTED, STATUS_PAUSED]:
                job_status = STATUS_RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_FAILED] and job_status != STATUS_FAILED:
            job_status = STATUS_FAILED

    elif compliant == STATUS_COMPLIANT_PYWPS:
        if job_status == STATUS_RUNNING:
            job_status = STATUS_STARTED
        elif job_status == STATUS_DISMISSED:
            job_status = STATUS_FAILED

    elif compliant == STATUS_COMPLIANT_OWSLIB:
        if job_status == STATUS_STARTED:
            job_status = STATUS_RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_FAILED] and job_status != STATUS_FAILED:
            job_status = STATUS_FAILED

    # TODO: patch for Geomatys not conforming to the status schema
    #       (status are upper cases and succeeded process are indicated as 'successful')
    if job_status == "successful":
        job_status = STATUS_SUCCEEDED

    if job_status in JOB_STATUS_VALUES:
        return job_status
    return STATUS_UNKNOWN
