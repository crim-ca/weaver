from typing import TYPE_CHECKING

from weaver.base import Constants

if TYPE_CHECKING:
    from typing import List

    from weaver.typedefs import TypedDict

    Conformance = TypedDict("Conformance", {
        "conformsTo": List[str]
    }, total=True)


class ConformanceCategory(Constants):
    ALL = "all"
    CONFORMANCE = "conf"
    PERMISSION = "per"
    RECOMMENDATION = "rec"
    REQUIREMENT = "req"


class JobInputsOutputsSchema(Constants):
    """
    Schema selector to represent a :term:`Job` output results.
    """
    OGC_STRICT = "ogc+strict"
    OLD_STRICT = "old+strict"
    OGC = "ogc"
    OLD = "old"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyConformanceCategory = Literal[
        ConformanceCategory.ALL,
        ConformanceCategory.CONFORMANCE,
        ConformanceCategory.PERMISSION,
        ConformanceCategory.RECOMMENDATION,
        ConformanceCategory.REQUIREMENT,
    ]

    JobInputsOutputsSchemaType = Literal[
        JobInputsOutputsSchema.OGC_STRICT,
        JobInputsOutputsSchema.OLD_STRICT,
        JobInputsOutputsSchema.OGC,
        JobInputsOutputsSchema.OLD
    ]
