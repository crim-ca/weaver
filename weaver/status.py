from typing import TYPE_CHECKING

from pywps.response.status import _WPS_STATUS, WPS_STATUS  # noqa: W0212

from weaver.base import Constants, ExtendedEnum


class StatusCompliant(ExtendedEnum):
    OGC = "OGC"
    PYWPS = "PYWPS"
    OWSLIB = "OWSLIB"


class StatusCategory(ExtendedEnum):
    FINISHED = "FINISHED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"


class Status(Constants):
    ACCEPTED = "accepted"
    STARTED = "started"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    RUNNING = "running"
    DISMISSED = "dismissed"
    EXCEPTION = "exception"
    UNKNOWN = "unknown"  # don't include in any below collections


JOB_STATUS_CATEGORIES = {
    # note:
    #   OGC compliant (old): [Accepted, Running, Succeeded, Failed]
    #   OGC compliant (new): [accepted, running, successful, failed, dismissed]
    #   PyWPS uses:          [Accepted, Started, Succeeded, Failed, Paused, Exception]
    #   OWSLib users:        [Accepted, Running, Succeeded, Failed, Paused] (with 'Process' in front)
    # https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/statusCode.yaml
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17

    # corresponding statuses are aligned vertically for 'COMPLIANT' groups
    StatusCompliant.OGC: frozenset([
        Status.ACCEPTED,
        Status.RUNNING,
        Status.SUCCEEDED,   # old (keep it because it matches existing ADES/EMS and other providers)
        Status.FAILED,
        Status.SUCCESSFUL,  # new
        Status.DISMISSED    # new
    ]),
    StatusCompliant.PYWPS: frozenset([
        Status.ACCEPTED,
        Status.STARTED,     # running
        Status.SUCCEEDED,
        Status.FAILED,
        Status.PAUSED,
        Status.EXCEPTION
    ]),
    StatusCompliant.OWSLIB: frozenset([
        Status.ACCEPTED,
        Status.RUNNING,
        Status.SUCCEEDED,
        Status.FAILED,
        Status.PAUSED
    ]),
    # utility categories
    StatusCategory.RUNNING: frozenset([
        Status.ACCEPTED,
        Status.RUNNING,
        Status.STARTED,
        Status.PAUSED
    ]),
    StatusCategory.FINISHED: frozenset([
        Status.FAILED,
        Status.DISMISSED,
        Status.EXCEPTION,
        Status.SUCCEEDED,
        Status.SUCCESSFUL
    ]),
    StatusCategory.FAILED: frozenset([
        Status.FAILED,
        Status.DISMISSED,
        Status.EXCEPTION
    ]),
}

# FIXME: see below detail in map_status about 'successful', partially compliant to OGC statuses
# https://github.com/opengeospatial/ogcapi-processes/blob/ca8e90/core/openapi/schemas/statusCode.yaml
JOB_STATUS_CODE_API = JOB_STATUS_CATEGORIES[StatusCompliant.OGC] - {Status.SUCCESSFUL}
JOB_STATUS_SEARCH_API = set(list(JOB_STATUS_CODE_API) + [StatusCategory.FINISHED.value.lower()])

# id -> str
STATUS_PYWPS_MAP = {s: _WPS_STATUS._fields[s].lower() for s in range(len(WPS_STATUS))}
# str -> id
STATUS_PYWPS_IDS = {k.lower(): v for v, k in STATUS_PYWPS_MAP.items()}

if TYPE_CHECKING:
    from typing import Union

    from weaver.typedefs import Literal

    StatusType = Literal[
        Status.ACCEPTED,
        Status.STARTED,
        Status.PAUSED,
        Status.SUCCEEDED,
        Status.FAILED,
        Status.RUNNING,
        Status.DISMISSED,
        Status.EXCEPTION,
        Status.UNKNOWN
    ]
    AnyStatusType = Union[Status, StatusType, int]

    AnyStatusCategory = Union[
        StatusCategory,
        Literal[
            StatusCategory.RUNNING,
            StatusCategory.FINISHED,
            StatusCategory.FAILED,
        ],
    ]

    AnyStatusOrCategory = Union[AnyStatusType, AnyStatusCategory]

    AnyStatusSearch = [
        Status,  # not 'AnyStatusType' to disallow 'int'
        StatusType,
        StatusCategory,
        AnyStatusCategory,
    ]


def map_status(wps_status, compliant=StatusCompliant.OGC):
    # type: (AnyStatusType, StatusCompliant) -> StatusType
    """
    Maps WPS execution statuses to between compatible values of different implementations.

    Mapping is supported for values from :mod:`weaver.status`, :mod:`OWSLib`, :mod:`pywps` as well as some
    specific one-of values of custom implementations.

    For each compliant combination, unsupported statuses are changed to corresponding ones (with closest logical match).
    Statuses are returned following :class:`Status` format.
    Specifically, this ensures statues are lowercase and not prefixed by ``Process``
    (as in XML response of OWS WPS like ``ProcessSucceeded`` for example).

    :param wps_status: One of :class:`Status` or its literal value to map to `compliant` standard.
    :param compliant: One of :class:`StatusCompliant` values.
    :returns: mapped status complying to the requested compliant category, or :data:`Status.UNKNOWN` if no match found.
    """

    # case of raw PyWPS status
    if isinstance(wps_status, int):
        return map_status(STATUS_PYWPS_MAP[wps_status], compliant)

    # remove 'Process' from OWSLib statuses and lower for every compliant
    job_status = str(wps_status).lower().replace("process", "")

    if compliant == StatusCompliant.OGC:
        if job_status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
            if job_status in [Status.STARTED, Status.PAUSED]:
                job_status = Status.RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]:
            if job_status not in [Status.FAILED, Status.DISMISSED]:
                job_status = Status.FAILED

    elif compliant == StatusCompliant.PYWPS:
        if job_status == Status.RUNNING:
            job_status = Status.STARTED
        elif job_status == Status.DISMISSED:
            job_status = Status.FAILED

    elif compliant == StatusCompliant.OWSLIB:
        if job_status == Status.STARTED:
            job_status = Status.RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FAILED] and job_status != Status.FAILED:
            job_status = Status.FAILED

    # FIXME: new official status is 'successful', but this breaks everywhere (tests, local/remote execute, etc.)
    #        https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/statusCode.yaml
    if job_status == Status.SUCCESSFUL:
        job_status = Status.SUCCEEDED

    if job_status in Status:
        return job_status
    return Status.UNKNOWN
