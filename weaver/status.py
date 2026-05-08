from typing import TYPE_CHECKING, cast, overload

from pywps.response.status import _WPS_STATUS, WPS_STATUS  # noqa: W0212

from weaver.base import Constants, ExtendedEnum


class StatusCompliant(ExtendedEnum):
    OGC = "OGC"
    PYWPS = "PYWPS"
    OWSLIB = "OWSLIB"
    OPENEO = "OPENEO"


class StatusCategory(ExtendedEnum):
    FINISHED = "FINISHED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"
    FAILED = "FAILED"
    SUCCESS = "SUCCESS"


class Status(Constants, str):
    CREATED = "created"         # type: Literal["created"]
    QUEUED = "queued"           # type: Literal["queued"]
    ACCEPTED = "accepted"       # type: Literal["accepted"]
    STARTED = "started"         # type: Literal["started"]
    PAUSED = "paused"           # type: Literal["paused"]
    SUCCEEDED = "succeeded"     # type: Literal["succeeded"]
    SUCCESSFUL = "successful"   # type: Literal["successful"]
    FAILED = "failed"           # type: Literal["failed"]
    ERROR = "error"             # type: Literal["error"]
    FINISHED = "finished"       # type: Literal["finished"]
    RUNNING = "running"         # type: Literal["running"]
    CANCELED = "canceled"       # type: Literal["canceled"]
    DISMISSED = "dismissed"     # type: Literal["dismissed"]
    EXCEPTION = "exception"     # type: Literal["exception"]
    UNKNOWN = "unknown"         # type: Literal["unknown"]  # don't include in any below collections


JOB_STATUS_CATEGORIES = {
    # note:
    #   OGC compliant (old): [Accepted, Running, successful, Failed]
    #   OGC compliant (new): [accepted, running, successful, failed, dismissed, created]  ('created' in Part 4 only)
    #   PyWPS uses:          [Accepted, Started, Succeeded, Failed, Paused, Exception]                  [WPS 1.0.0]
    #   OWSLib uses:         [Accepted, Running, Succeeded, Failed, Paused] (with 'Process' in front)   [WPS 2.0]
    #   OpenEO uses:         [queued, running, finished, error, canceled, created]
    # https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas/processes-core/statusCode.yaml
    # http://docs.opengeospatial.org/is/14-065/14-065.html#17
    # https://schemas.opengis.net/wps/1.0.0/wpsExecute_response.xsd
    # https://schemas.opengis.net/wps/2.0/wpsCommon.xsd

    # corresponding statuses are aligned vertically for 'COMPLIANT' groups
    StatusCompliant.OGC: frozenset([
        Status.CREATED,     # Part 4: Job Management
        Status.ACCEPTED,
        Status.RUNNING,
        Status.FAILED,
        Status.SUCCESSFUL,  # v1/v2 official (alternative "SUCCEEDED" was in v2-draft for a while)
        Status.DISMISSED    # new
    ]),
    StatusCompliant.PYWPS: frozenset([
        Status.ACCEPTED,
        Status.STARTED,     # running
        Status.SUCCEEDED,
        Status.FAILED,
        Status.PAUSED
    ]),
    StatusCompliant.OWSLIB: frozenset([
        Status.ACCEPTED,
        Status.RUNNING,
        Status.SUCCEEDED,
        Status.FAILED,
        Status.PAUSED
    ]),
    StatusCompliant.OPENEO: frozenset([
        Status.CREATED,
        Status.QUEUED,
        Status.RUNNING,
        Status.FINISHED,
        Status.ERROR,
        Status.CANCELED
    ]),
    # utility categories
    StatusCategory.RUNNING: frozenset([
        Status.ACCEPTED,
        Status.RUNNING,
        Status.STARTED,
        Status.QUEUED,
        Status.PAUSED
    ]),
    StatusCategory.PENDING: frozenset([
        Status.CREATED,
        Status.ACCEPTED,
        Status.QUEUED,
        Status.PAUSED
    ]),
    StatusCategory.FINISHED: frozenset([
        Status.FAILED,
        Status.DISMISSED,
        Status.CANCELED,
        Status.EXCEPTION,
        Status.ERROR,
        Status.SUCCEEDED,
        Status.SUCCESSFUL,
        Status.FINISHED
    ]),
    StatusCategory.SUCCESS: frozenset([
        Status.SUCCEEDED,
        Status.SUCCESSFUL,
        Status.FINISHED
    ]),
    StatusCategory.FAILED: frozenset([
        Status.FAILED,
        Status.DISMISSED,
        Status.EXCEPTION,
        Status.ERROR
    ]),
}

JOB_STATUS_CODE_API = JOB_STATUS_CATEGORIES[StatusCompliant.OGC]
JOB_STATUS_SEARCH_API = set(Status.values()) - {Status.UNKNOWN}  # allow any variant for various profile support

# id -> str
STATUS_PYWPS_MAP = {s: _WPS_STATUS._fields[s].lower() for s in range(len(WPS_STATUS))}
# str -> id
STATUS_PYWPS_IDS = {k.lower(): v for v, k in STATUS_PYWPS_MAP.items()}

if TYPE_CHECKING:
    from typing import Any, Union
    from typing_extensions import Annotated

    from weaver.typedefs import Literal

    # Using Annotated to preserve origin references while using valid literal types
    StatusType = Union[
        Annotated[Literal["created"], Status.CREATED],
        Annotated[Literal["accepted"], Status.ACCEPTED],
        Annotated[Literal["started"], Status.STARTED],
        Annotated[Literal["queued"], Status.QUEUED],
        Annotated[Literal["paused"], Status.PAUSED],
        Annotated[Literal["succeeded"], Status.SUCCEEDED],
        Annotated[Literal["successful"], Status.SUCCESSFUL],
        Annotated[Literal["finished"], Status.FINISHED],
        Annotated[Literal["failed"], Status.FAILED],
        Annotated[Literal["running"], Status.RUNNING],
        Annotated[Literal["dismissed"], Status.DISMISSED],
        Annotated[Literal["canceled"], Status.CANCELED],
        Annotated[Literal["exception"], Status.EXCEPTION],
        Annotated[Literal["error"], Status.ERROR],
        Annotated[Literal["unknown"], Status.UNKNOWN],
    ]
    AnyStatusType = Union[Status, StatusType, int]

    # Using Annotated for StatusCategory enum members as well
    StatusCategoryType = Union[
        Annotated[Literal["RUNNING"], StatusCategory.RUNNING],
        Annotated[Literal["PENDING"], StatusCategory.PENDING],
        Annotated[Literal["FINISHED"], StatusCategory.FINISHED],
        Annotated[Literal["FAILED"], StatusCategory.FAILED],
        Annotated[Literal["SUCCESS"], StatusCategory.SUCCESS],
    ]
    AnyStatusCategory = Union[StatusCategory, StatusCategoryType]

    AnyStatusOrCategory = Union[AnyStatusType, AnyStatusCategory]

    AnyStatusSearch = Union[
        Status,   # not 'AnyStatusType' to disallow 'int'
        StatusType,
        StatusCategory,
        StatusCategoryType,
    ]


@overload
def map_status(wps_status):
    # type: (AnyStatusType) -> StatusType
    ...


@overload
def map_status(wps_status, compliant):
    # type: (AnyStatusType, StatusCompliant) -> StatusType
    ...


@overload
def map_status(wps_status, *, category):
    # type: (AnyStatusType, Any, Literal[True]) -> StatusCategory
    ...


def map_status(wps_status, compliant=StatusCompliant.OGC, category=False):  # pylint: disable=R1260
    # type: (AnyStatusType, StatusCompliant, bool) -> Union[StatusType, StatusCategory]
    """
    Maps execution statuses between compatible values of different implementations.

    Mapping is supported for values from :mod:`weaver.status`, :mod:`OWSLib`, :mod:`pywps`, :term:`openEO`,
    as well as some specific one-of values of custom :term:`OAP` implementations.

    For each compliant combination, unsupported statuses are changed to corresponding ones with the
    closest logical match. Statuses are returned following :class:`Status` format.
    Specifically, this ensures statues are lowercase and not prefixed by ``Process``
    (as in :term:`XML` response of :term:`OWS` :term:`WPS` like ``ProcessSucceeded`` for example).

    :param wps_status: One of :class:`Status` or its literal value to map to `compliant` standard.
    :param compliant: One of :class:`StatusCompliant` values.
    :param category: Request that the :class:`StatusCategory` corresponding to the supplied status is returned.
    :returns: Mapped status complying to the requested compliant category, or :data:`Status.UNKNOWN` if no match found.
    """
    compliant = StatusCompliant.get(compliant) or StatusCompliant.OGC

    # case of raw PyWPS status
    if isinstance(wps_status, int):
        return map_status(STATUS_PYWPS_MAP[wps_status], compliant)

    # remove 'Process' from OWSLib statuses and lower for every compliant
    job_status = str(wps_status).lower().replace("process", "")

    if category:
        # order important to prioritize most restrictive
        # categories with overlapping statuses first
        for status_category in [
            StatusCategory.SUCCESS,
            StatusCategory.FAILED,
            StatusCategory.RUNNING,
            StatusCategory.PENDING,
            StatusCategory.FINISHED,
        ]:
            if job_status in JOB_STATUS_CATEGORIES[status_category]:
                return status_category
        return Status.UNKNOWN

    elif compliant == StatusCompliant.OGC:
        if job_status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
            if job_status in [Status.STARTED, Status.PAUSED]:
                return Status.RUNNING
            elif job_status in [Status.QUEUED]:
                return Status.ACCEPTED
        elif job_status in [Status.CANCELED, Status.DISMISSED]:
            return Status.DISMISSED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]:
            return Status.FAILED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.SUCCESS]:
            return Status.SUCCESSFUL

    elif compliant == StatusCompliant.PYWPS:
        if job_status in [Status.RUNNING]:
            return Status.STARTED
        elif job_status in [Status.ACCEPTED]:
            return Status.ACCEPTED
        elif job_status in [Status.DISMISSED, Status.CANCELED]:
            return Status.FAILED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]:
            return Status.FAILED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.PENDING]:
            return Status.PAUSED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            return Status.SUCCEEDED

    elif compliant == StatusCompliant.OWSLIB:
        if job_status in JOB_STATUS_CATEGORIES[StatusCategory.PENDING]:
            return Status.PAUSED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
            return Status.RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]:
            return Status.FAILED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            return Status.SUCCEEDED

    elif compliant == StatusCompliant.OPENEO:
        if job_status in JOB_STATUS_CATEGORIES[StatusCategory.PENDING]:
            return Status.QUEUED
        elif job_status in [Status.DISMISSED]:
            return Status.CANCELED
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.RUNNING]:
            return Status.RUNNING
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FAILED]:
            return Status.ERROR
        elif job_status in JOB_STATUS_CATEGORIES[StatusCategory.FINISHED]:
            return Status.FINISHED

    if job_status in Status:
        return cast("StatusType", job_status)
    return Status.UNKNOWN
