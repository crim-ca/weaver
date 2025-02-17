from typing import TYPE_CHECKING

from weaver.base import Constants

if TYPE_CHECKING:
    from typing import List

    from weaver.typedefs import TypedDict, Union

    Conformance = TypedDict("Conformance", {
        "conformsTo": List[str]
    }, total=True)


class ConformanceCategory(Constants):
    ALL = "all"
    CONFORMANCE = "conf"
    PERMISSION = "per"
    RECOMMENDATION = "rec"
    REQUIREMENT = "req"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyConformanceCategory = Union[
        ConformanceCategory,
        Literal[
            ConformanceCategory.ALL,
            ConformanceCategory.CONFORMANCE,
            ConformanceCategory.PERMISSION,
            ConformanceCategory.RECOMMENDATION,
            ConformanceCategory.REQUIREMENT,
        ]
    ]
