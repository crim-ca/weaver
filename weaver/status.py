from typing import TYPE_CHECKING

from pywps.response.status import _WPS_STATUS, WPS_STATUS  # noqa: W0212

STATUS_COMPLIANT_OGC = "STATUS_COMPLIANT_OGC"
STATUS_COMPLIANT_PYWPS = "STATUS_COMPLIANT_PYWPS"
STATUS_COMPLIANT_OWSLIB = "STATUS_COMPLIANT_OWSLIB"
JOB_STATUS_CATEGORY_FINISHED = "JOB_STATUS_CATEGORY_FINISHED"
JOB_STATUS_CATEGORY_RUNNING = "JOB_STATUS_CATEGORY_RUNNING"
JOB_STATUS_CATEGORY_FAILED = "JOB_STATUS_CATEGORY_FAILED"

STATUS_ACCEPTED = "accepted"
STATUS_STARTED = "started"
STATUS_PAUSED = "paused"
STATUS_SUCCEEDED = "succeeded"
STATUS_SUCCESSFUL = "successful"
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

JOB_STATUS_CATEGORIES = {
    # note:
    #   OGC compliant (old): [Accepted, Running, Succeeded, Failed]
    #   OGC compliant (new): [accepted, running, successful, failed, dismissed]
    #   PyWPS uses:          [Accepted, Started, Succeeded, Failed, Paused, Exception]
    #   OWSLib users:        [Accepted, Running, Succeeded, Failed, Paused] (with 'Process' in front)
    # https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/statusCode.yaml
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17

    # corresponding statuses are aligned vertically for 'COMPLIANT' groups
    STATUS_COMPLIANT_OGC: frozenset([
        STATUS_ACCEPTED,
        STATUS_RUNNING,
        STATUS_SUCCEEDED,   # old (keep it because it matches existing ADES/EMS and other providers)
        STATUS_FAILED,
        STATUS_SUCCESSFUL,  # new
        STATUS_DISMISSED    # new
    ]),
    STATUS_COMPLIANT_PYWPS: frozenset([
        STATUS_ACCEPTED,
        STATUS_STARTED,     # running
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_PAUSED,
        STATUS_EXCEPTION
    ]),
    STATUS_COMPLIANT_OWSLIB: frozenset([
        STATUS_ACCEPTED,
        STATUS_RUNNING,
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_PAUSED
    ]),
    # utility categories
    JOB_STATUS_CATEGORY_RUNNING: frozenset([
        STATUS_ACCEPTED,
        STATUS_RUNNING,
        STATUS_STARTED,
        STATUS_PAUSED
    ]),
    JOB_STATUS_CATEGORY_FINISHED: frozenset([
        STATUS_FAILED,
        STATUS_DISMISSED,
        STATUS_EXCEPTION,
        STATUS_SUCCEEDED,
        STATUS_SUCCESSFUL
    ]),
    JOB_STATUS_CATEGORY_FAILED: frozenset([
        STATUS_FAILED,
        STATUS_DISMISSED,
        STATUS_EXCEPTION
    ]),
}

# FIXME: see below detail in map_status about 'successful', partially compliant to OGC statuses
# https://github.com/opengeospatial/ogcapi-processes/blob/ca8e90/core/openapi/schemas/statusCode.yaml
JOB_STATUS_CODE_API = JOB_STATUS_CATEGORIES[STATUS_COMPLIANT_OGC] - {STATUS_SUCCESSFUL}

# id -> str
STATUS_PYWPS_MAP = {s: _WPS_STATUS._fields[s].lower() for s in range(len(WPS_STATUS))}
# str -> id
STATUS_PYWPS_IDS = {k.lower(): v for v, k in STATUS_PYWPS_MAP.items()}


def map_status(wps_status, compliant=STATUS_COMPLIANT_OGC):
    # type: ("AnyStatusType", str) -> str
    """
    Maps WPS execution statuses to between compatible values of different implementations.

    Mapping is supported for values from :mod:`weaver.status`, :mod:`OWSLib`, :mod:`pywps` as well as some
    specific one-of values of custom implementations.

    For each compliant combination, unsupported statuses are changed to corresponding ones (with closest logical match).
    Statuses are returned following :data:`weaver.status.JOB_STATUS_VALUES` format.
    Specifically, this ensures statues are lowercase and not prefixed by ``Process``
    (as in XML response of OWS WPS like ``ProcessSucceeded`` for example).

    :param wps_status:
        One of :data:`weaver.status.JOB_STATUS_VALUES` to map to `compliant` standard or PyWPS `int` status.
    :param compliant: One of ``STATUS_COMPLIANT_[...]`` values.
    :returns: mapped status complying to the requested compliant category, or :data:`STATUS_UNKNOWN` if no match found.
    """

    # case of raw PyWPS status
    if isinstance(wps_status, int):
        return map_status(STATUS_PYWPS_MAP[wps_status], compliant)

    # remove 'Process' from OWSLib statuses and lower for every compliant
    job_status = wps_status.lower().replace("process", "")

    if compliant == STATUS_COMPLIANT_OGC:
        if job_status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_RUNNING]:
            if job_status in [STATUS_STARTED, STATUS_PAUSED]:
                job_status = STATUS_RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_FAILED]:
            if job_status not in [STATUS_FAILED, STATUS_DISMISSED]:
                job_status = STATUS_FAILED

    elif compliant == STATUS_COMPLIANT_PYWPS:
        if job_status == STATUS_RUNNING:
            job_status = STATUS_STARTED
        elif job_status == STATUS_DISMISSED:
            job_status = STATUS_FAILED

    elif compliant == STATUS_COMPLIANT_OWSLIB:
        if job_status == STATUS_STARTED:
            job_status = STATUS_RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[JOB_STATUS_CATEGORY_FAILED] and job_status != STATUS_FAILED:
            job_status = STATUS_FAILED

    # FIXME: new official status is 'successful', but this breaks everywhere (tests, local/remote execute, etc.)
    #        https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/statusCode.yaml
    if job_status == STATUS_SUCCESSFUL:
        job_status = STATUS_SUCCEEDED

    if job_status in JOB_STATUS_VALUES:
        return job_status
    return STATUS_UNKNOWN


if TYPE_CHECKING:
    from typing import Union

    from weaver.typedefs import Literal

    StatusType = Literal[
        STATUS_ACCEPTED,
        STATUS_STARTED,
        STATUS_PAUSED,
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_RUNNING,
        STATUS_DISMISSED,
        STATUS_EXCEPTION,
        STATUS_UNKNOWN
    ]
    AnyStatusType = Union[StatusType, int]
